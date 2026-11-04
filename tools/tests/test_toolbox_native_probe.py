import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'etm-service/tools'))
from native_probe import NativeProbe, install,reset_dap_session


class NativeProbeTests(unittest.TestCase):
    def test_session_cancel_routes_capture_to_its_existing_stop_transaction(self):
        owner='a'*32
        backend=SimpleNamespace(lock=threading.RLock(),ACTIVE=('armed',),
            jobs={'job':{'restoreOwner':owner,'state':'armed'}},
            stop_capture=Mock(return_value=SimpleNamespace(get_json=lambda:{'ok':True})))
        with tempfile.TemporaryDirectory() as folder:
            token=Path(folder)/'token';token.write_text('c'*64)
            proxy=NativeProbe(backend,token)
            result=proxy.session_call('cancel',{'owner':owner})
            self.assertTrue(result['captureStop']['ok']);backend.stop_capture.assert_called_once_with('job')
    def _hss_proxy(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        token=Path(folder.name)/'token';token.write_text('c'*64)
        backend=SimpleNamespace(lock=threading.RLock(),jobs={},ACTIVE=('queued',))
        proxy=NativeProbe(backend,token);device=Mock()
        proxy.usb=device;proxy.usb_owner='a'*32;proxy.usb_epoch='epoch';proxy.claimed={0}
        return proxy,device

    def test_hss_read_preserves_partial_batch_in_one_bulk_request(self):
        import base64
        proxy,device=self._hss_proxy()
        receiver=Mock();receiver.read.return_value=bytes(range(256))*6
        proxy.hss_receiver=receiver
        result=proxy.usb_call('read',dict(owner='a'*32,resourceEpoch='epoch',endpoint=0x87,length=65536))
        self.assertEqual(base64.b64decode(result['data']),bytes(range(256))*6)
        self.assertFalse(result['timedOut'])
        receiver.read.assert_called_once_with(65536)

    def test_hss_empty_timeout_is_an_empty_completion_for_confirmed_drain(self):
        import usb.core
        proxy,device=self._hss_proxy()
        receiver=Mock();receiver.read.return_value=b'';proxy.hss_receiver=receiver
        proxy.usb=device;proxy.usb_owner='a'*32;proxy.usb_epoch='epoch';proxy.claimed={0}
        self.assertEqual(proxy.usb_call('read',dict(owner='a'*32,resourceEpoch='epoch',endpoint=0x87,length=65536)),{'data':'','timedOut':True})

    def test_hss_receiver_is_stopped_before_usb_release(self):
        proxy,device=self._hss_proxy();receiver=Mock();proxy.hss_receiver=receiver
        with patch('usb.util.release_interface') as release:
            proxy.usb_call('release',dict(owner='a'*32,resourceEpoch='epoch',number=0))
            receiver.close.assert_called_once();release.assert_called_once_with(device,0)
        self.assertIsNone(proxy.hss_receiver)

    def test_installed_libusb1_backend_returns_timeout_partial_bytes(self):
        # Exercise the actual backend read contract without opening a device.
        import array,ctypes,usb.backend.libusb1 as libusb1
        buffer=array.array('B',[0])*4096
        def transfer(handle,ep,data,length,transferred,timeout):
            for n in range(512):data[n]=n&255
            ctypes.cast(transferred,ctypes.POINTER(ctypes.c_int))[0]=512
            return libusb1.LIBUSB_ERROR_TIMEOUT
        count=libusb1._LibUSB._LibUSB__read(None,transfer,SimpleNamespace(handle=None),0x87,0,buffer,40)
        self.assertEqual(count,512)
        self.assertEqual(buffer[:count].tobytes(),bytes(range(256))*2)

    def test_atomic_dap_exchange_sends_once_then_reads_the_same_epoch(self):
        import base64
        backend=SimpleNamespace(lock=threading.RLock(),jobs={},ACTIVE=('queued',))
        with tempfile.TemporaryDirectory() as folder:
            token=Path(folder)/'token';token.write_text('c'*64);proxy=NativeProbe(backend,token)
            device=Mock();device.write.return_value=2;device.read.return_value=b'\x00\x00'
            proxy.usb=device;proxy.usb_owner='a'*32;proxy.usb_epoch='epoch';proxy.claimed={0}
            result=proxy.usb_call('exchange',dict(owner='a'*32,resourceEpoch='epoch',data=base64.b64encode(b'\0\xff').decode(),length=512,timeoutMs=1000))
            self.assertEqual(base64.b64decode(result['data']),b'\0\0');self.assertFalse(result['timedOut'])
            device.write.assert_called_once();device.read.assert_called_once()
            self.assertLessEqual(device.read.call_args.kwargs['timeout'],1000)

    def test_atomic_dap_exchange_rejects_short_write_without_read_or_replay(self):
        backend=SimpleNamespace(lock=threading.RLock(),jobs={},ACTIVE=('queued',))
        with tempfile.TemporaryDirectory() as folder:
            token=Path(folder)/'token';token.write_text('c'*64);proxy=NativeProbe(backend,token)
            device=Mock();device.write.return_value=1
            proxy.usb=device;proxy.usb_owner='a'*32;proxy.usb_epoch='epoch';proxy.claimed={0}
            with self.assertRaisesRegex(ValueError,'短写'):
                proxy.usb_call('exchange',dict(owner='a'*32,resourceEpoch='epoch',data='AP8=',length=512,timeoutMs=1000))
            device.write.assert_called_once();device.read.assert_not_called()
    def test_dap_epoch_reset_uses_no_speculative_bulk_reads_or_whole_usb_reset(self):
        import struct
        device=Mock()
        device.ctrl_transfer.side_effect=[struct.pack('<8I',0,2,1,7,0,0,0,0),b'DAP\0',struct.pack('<8I',0,0,0,8,0,0,0,0)]
        result=reset_dap_session(device)
        self.assertEqual(result,dict(syncProtocol='zynq-dap-epoch/1',queueEpoch=8,queueState=[0,0,0]))
        self.assertEqual([c.args[1] for c in device.ctrl_transfer.call_args_list],[0x5b,0x5a,0x5b])
        self.assertEqual([c.args for c in device.clear_halt.call_args_list],[(0x81,),(2,)])
        device.read.assert_not_called();device.write.assert_not_called();device.reset.assert_not_called()

    def test_dap_epoch_reset_requires_idle_queues_and_a_new_epoch(self):
        import struct
        for tail in [(0,0,0,7,0,0,0,0),(0,1,1,8,0,0,0,0)]:
            device=Mock();device.ctrl_transfer.side_effect=[struct.pack('<8I',0,0,0,7,0,0,0,0),b'DAP\0',struct.pack('<8I',*tail)]
            with self.assertRaisesRegex(ValueError,'epoch'):reset_dap_session(device)
    def test_late_close_cannot_close_a_reopened_usb_or_hid_handle(self):
        backend=SimpleNamespace(lock=threading.RLock(),jobs={},ACTIVE=('queued',))
        with tempfile.TemporaryDirectory() as folder:
            token=Path(folder)/'token';token.write_text('c'*64)
            proxy=NativeProbe(backend,token);device=object()
            proxy.usb=proxy.hid=device;proxy.usb_owner=proxy.hid_owner='a'*32
            proxy.usb_epoch=proxy.hid_epoch='new'
            old={'owner':'a'*32,'resourceEpoch':'old'}
            self.assertTrue(proxy.usb_call('close',old)['superseded'])
            self.assertTrue(proxy.hid_call('close',old)['superseded'])
            self.assertIs(proxy.usb,device);self.assertIs(proxy.hid,device)

    def test_native_serial_honors_the_web_requested_receive_buffer(self):
        class Port:
            def set_buffer_size(self,**kwargs):self.sizes=kwargs
            def read(self,n):return b''
            def close(self):pass
        with tempfile.TemporaryDirectory() as folder:
            token=Path(folder)/'token';token.write_text('c'*64)
            proxy=NativeProbe(SimpleNamespace(),token);port=Port()
            with patch('serial.tools.list_ports.comports',return_value=[SimpleNamespace(device='COM33')]),patch('serial.Serial',return_value=port):
                proxy.serial_call('open',{'owner':'a'*32,'path':'COM33','options':{'bufferSize':65536}})
                self.assertEqual(port.sizes,{'rx_size':65536,'tx_size':65536})
                self.assertIs(proxy.ports[('a'*32,'COM33')],port)
                proxy.serial_call('close',{'owner':'a'*32,'path':'COM33'})

    def test_http_redelivery_returns_the_original_result_without_hardware_reexecution(self):
        with tempfile.TemporaryDirectory() as folder:
            token=Path(folder)/'token';token.write_text('c'*64)
            proxy=NativeProbe(SimpleNamespace(),token)
            calls=[]
            def operation():
                calls.append('USB write/read')
                return ({'ok':True,'value':{'data':'real USB reply'}},200)
            identity='a'*32;body={'action':'write','data':'abc'}
            first=proxy.deliver(identity,body,operation)
            self.assertEqual(proxy.deliver(identity,body,operation),first)
            self.assertEqual(len(calls),1)
            with self.assertRaisesRegex(ValueError,'内容不一致'):
                proxy.deliver(identity,{'action':'reset'},operation)
            del proxy.delivery_cache[identity]
            with self.assertRaisesRegex(ValueError,'拒绝重放'):
                proxy.deliver(identity,body,operation)
            self.assertEqual(len(calls),1)

    def test_serial_reopen_cannot_cross_an_old_read_epoch_check(self):
        checked=threading.Event();release=threading.Event();opening=threading.Event();opened=threading.Event()
        class Epochs(dict):
            def get(self,key,default=None):
                value=super().get(key,default)
                if threading.current_thread().name=='old-read':
                    checked.set();self.assert_release()
                return value
            def assert_release(self):
                if not release.wait(2):raise RuntimeError('test barrier timed out')
        class Port:
            closed=False
            def __init__(self,data=b''):self.data=data
            def read(self,n):data,self.data=self.data,b'';return data
            def close(self):self.closed=True
            def set_buffer_size(self,**kw):pass
        class Receiver:
            def read(self):return b'old bytes'
            def close(self):pass
        with tempfile.TemporaryDirectory()as folder:
            token=Path(folder)/'token';token.write_text('c'*64);proxy=NativeProbe(SimpleNamespace(),token)
            key=('a'*32,'COM33');old=Port();new=Port(b'new bytes');proxy.ports[key]=old
            proxy.serial_receivers[key]=Receiver();proxy.port_epochs=Epochs({key:'old'})
            output=[];errors=[]
            def read():
                try:output.append(proxy.serial_call('read',dict(owner=key[0],path=key[1],resourceEpoch='old')))
                except Exception as e:errors.append(e)
            def reopen():
                opening.set()
                try:output.append(proxy.serial_call('open',dict(owner=key[0],path=key[1])))
                except Exception as e:errors.append(e)
                finally:opened.set()
            with patch('serial.tools.list_ports.comports',return_value=[SimpleNamespace(device='COM33')]),patch('serial.Serial',return_value=new):
                reader=threading.Thread(target=read,name='old-read');reader.start();self.assertTrue(checked.wait(1))
                opener=threading.Thread(target=reopen);opener.start();self.assertTrue(opening.wait(1))
                try:self.assertFalse(opened.wait(.05),'Reopen crossed the old epoch check')
                finally:release.set();reader.join(2);opener.join(2)
            self.assertFalse(reader.is_alive());self.assertFalse(opener.is_alive());self.assertFalse(errors,errors)
            self.assertEqual(output[0]['data'],'b2xkIGJ5dGVz')
            self.assertIs(proxy.ports[key],new)
            self.assertTrue(proxy.serial_call('close',dict(owner=key[0],path=key[1],resourceEpoch='old'))['superseded'])
            self.assertFalse(new.closed)
            self.assertEqual(proxy.serial_call('read',dict(owner=key[0],path=key[1],resourceEpoch=proxy.port_epochs[key]))['data'],'bmV3IGJ5dGVz')
            proxy.serial_call('close',dict(owner=key[0],path=key[1],resourceEpoch=proxy.port_epochs[key]))

    def test_sequence_delivery_survives_100000_requests_with_bounded_replay_history(self):
        with tempfile.TemporaryDirectory() as folder:
            token=Path(folder)/'token';token.write_text('c'*64)
            proxy=NativeProbe(SimpleNamespace(),token)
            calls=[0]
            def execute():calls[0]+=1;return ({'ok':True,'value':calls[0]},200)
            session='d'*32
            # Out-of-order in-flight arrivals within the window are legal.
            proxy.deliver('v2:'+session+':2',{},execute)
            proxy.deliver('v2:'+session+':1',{},execute)
            for seq in range(3,100010):proxy.deliver(f'v2:{session}:{seq}',{},execute)
            self.assertEqual(calls[0],100009)
            last=proxy.deliver(f'v2:{session}:100009',{},execute)
            self.assertEqual(last[0]['value'],100009)
            self.assertEqual(calls[0],100009)
            with self.assertRaisesRegex(ValueError,'拒绝重放'):proxy.deliver('v2:'+session+':1',{},execute)
            self.assertLessEqual(len(proxy.delivery_cache),256)
            self.assertEqual(len(proxy.delivery_sessions),1)
            self.assertLessEqual(proxy.delivery_sessions[session][1].bit_length(),4096)
            self.assertFalse(proxy.delivery_seen)
            with self.assertRaisesRegex(ValueError,'内容不一致'):
                proxy.deliver(f'v2:{session}:100009',{'action':'reset'},execute)
            self.assertEqual(calls[0],100009)

    def test_loopback_token_and_origin_are_required_before_hardware_dispatch(self):
        from flask import Flask
        app = Flask('native_probe_test')
        backend = SimpleNamespace(app=Flask('backend'), lock=threading.RLock(), jobs={}, ACTIVE=('queued', 'starting'))
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder) / 'token'; token.write_text('c' * 64)
            proxy = install(app, backend, token)
            with app.test_client() as client, patch.object(proxy, 'usb_call', return_value=[{'realTransport': True}]) as hardware:
                self.assertEqual(client.post('/native-probe/usb/list', json={}).status_code, 403)
                headers = {'X-Trace-CLI': 'c' * 64}
                self.assertEqual(client.post('/native-probe/usb/list', json={}, headers={**headers, 'Origin': 'https://example.com'}).status_code, 403)
                hardware.assert_not_called()
                result = client.post('/native-probe/usb/list', json={}, headers=headers)
                self.assertEqual(result.status_code, 200)
                self.assertTrue(result.json['value'][0]['realTransport'])

    def test_other_owner_cannot_close_an_active_usb_session(self):
        backend = SimpleNamespace(lock=threading.RLock(), jobs={}, ACTIVE=('queued',))
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder) / 'token'; token.write_text('c' * 64)
            proxy = NativeProbe(backend, token)
            device = object(); proxy.usb = device; proxy.usb_owner = 'a' * 32
            self.assertEqual(proxy.usb_call('close', {'owner': 'b' * 32}), {'closed': True})
            self.assertIs(proxy.usb, device)
            with self.assertRaisesRegex(ValueError, '另一Web会话'):
                proxy.usb_call('open', {'owner': 'b' * 32})
            backend.jobs['capture'] = {'kind': 'capture', 'state': 'queued'}
            with self.assertRaisesRegex(ValueError, 'ETM'):
                proxy.usb_call('open', {'owner': 'a' * 32})

    def test_binary_limits_and_capture_cleanup_guard(self):
        with self.assertRaises(Exception):
            NativeProbe.blob('not base64')
        with self.assertRaises(ValueError):
            NativeProbe.blob('YWI=', 1)
        self.assertEqual(NativeProbe.blob('AID/'), bytes([0, 128, 255]))


if __name__ == '__main__':
    unittest.main()
