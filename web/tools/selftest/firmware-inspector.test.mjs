import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {inspectElf,elfTable,firmwareRegions,hexPage} from '../../app/flash/inspect.js';
import {parseIntelHex} from '../../app/flash/image.js';
import {programOpenOcdFlash} from '../../app/flash/openocd-program.js';

test('real ARM and H743 ELF headers, sections and symbols are inspectable without target access',()=>{
  for(const name of ['prebuilt/golden/f103ze-cdc48.elf','prebuilt/targets/stm32h743-cdc-trace-20261101/cpu60-trace20/fw.elf']){
    const b=new Uint8Array(fs.readFileSync(name)),elf=inspectElf(b);
    assert.equal(new Map(elf.header).get('机器'),'ARM');
    assert.ok(elf.programs.some(p=>p.type===1));assert.ok(elf.sections.some(s=>s.name==='.text'));
    const symbols=elfTable(elf,'symbols','main');assert.ok(symbols.rows.some(r=>r[2]==='main'));
    assert.ok(symbols.total>=symbols.rows.length);
    assert.ok(firmwareRegions(name,b,'bad unused base').length);
  }
});
test('ELF64 big-endian keeps addresses beyond JS integer precision and permits no section table',()=>{
  const b=new Uint8Array(64),d=new DataView(b.buffer);b.set([127,69,76,70,2,2,1]);d.setUint16(16,2);d.setUint16(18,183);d.setBigUint64(24,0x100000000000001n);d.setUint16(52,64);
  const elf=inspectElf(b);assert.equal(new Map(elf.header).get('入口'),'0x100000000000001');assert.equal(elf.symbols().total,0);
});
test('ELF rejects truncated tables, invalid endian and out-of-file section data',()=>{
  const original=new Uint8Array(fs.readFileSync('prebuilt/golden/f103ze-cdc48.elf'));
  assert.throws(()=>inspectElf(original.subarray(0,100)),/越界|截断/);
  const b=original.slice();b[5]=0;assert.throws(()=>inspectElf(b),/端序/);
  b[5]=1;const d=new DataView(b.buffer),sh=d.getUint32(32,true),ent=d.getUint16(46,true);d.setUint32(sh+ent+16,0xfffffff0,true);assert.throws(()=>inspectElf(b),/越界/);
});
test('sparse HEX preserves region addresses, reports checksum failure, and raw bytes are not HEX text',()=>{
  const text=':020000040800F2\n:0400000001020304F2\n:0400080005060708DA\n:00000001FF';
  const bytes=new TextEncoder().encode(text),r=firmwareRegions('two.hex',bytes,0);
  assert.equal(r.length,2);assert.equal(r[1].addr,0x08000008);assert.deepEqual([...r[0].data],[1,2,3,4]);
  assert.throws(()=>firmwareRegions('bad.hex',new TextEncoder().encode(text.replace('F2','F3')),0),/校验和/);
});
test('BIN base validation matches programming, page boundaries and ASCII stay explicit',()=>{
  const b=Uint8Array.from({length:1025},(_,i)=>i&255),r=firmwareRegions('data.bin',b,'0x08000000');assert.equal(r[0].addr,0x08000000);
  assert.equal(firmwareRegions('data.bin',b,'0x00000000')[0].addr,0);
  assert.throws(()=>firmwareRegions('data.bin',b,' '),/基地址/);
  assert.throws(()=>firmwareRegions('data.bin',b,'0xffffffff'),/超过/);
  assert.equal(hexPage(b,0,1024).split('\n').length,1);
  assert.match(hexPage(new Uint8Array([60,115,62,0]),0x8000000),/3C 73 3E 00.*\|<s>\.\|/);
});

test('sparse HEX changes only explicit bytes in the programmed sector', async () => {
  const regions = parseIntelHex(':020000040800F2\n:01000000A55A\n:010008005A9D\n:00000001FF');
  let sector = Uint8Array.from({length:16}, (_, i) => 0x80 + i);
  const original = sector.slice();
  let image;
  const probe = {
    async command(line){
      if (line === 'capture {flash banks}' || line.includes('flash info'))
        return '#0 : sample (stm32f1x) at 0x08000000, size 0x00000010\n # 0: 0x00000000 (0x00000010 0 KiB)';
      if (line.startsWith('flash erase_sector')) sector.fill(0xff);
      if (line.startsWith('flash write_bank')) sector = image.slice();
      return '';
    },
    link:{ async request(_type, payload){
      if (payload?.input) image = payload.input;
      if (payload?.read) return { bytes:sector.slice() };
      return {};
    } },
  };
  const result = await programOpenOcdFlash(probe, regions, { verify:true, progress(){} });
  assert.deepEqual(result, { bytes:2, sectors:1, verified:true });
  original[0] = 0xa5;
  original[8] = 0x5a;
  assert.deepEqual(sector, original);
});

test('HEX merges a 64 KiB consecutive run with exact byte ordering and rejects overlap', () => {
  const rows = Array.from({length:4096}, (_, i) => {
    const address = i * 16;
    const data = Array.from({length:16}, (_, j) => (i + j) & 255);
    const bytes = [16, address >> 8, address & 255, 0, ...data];
    bytes.push(-bytes.reduce((sum, b) => sum + b, 0) & 255);
    return ':' + bytes.map(b => b.toString(16).padStart(2, '0')).join('');
  });
  const regions = parseIntelHex([...rows, ':00000001FF'].join('\n'));
  assert.equal(regions.length, 1);
  assert.equal(regions[0].addr, 0);
  assert.equal(regions[0].data.length, 65536);
  assert.ok(regions[0].data.every((byte, i) => byte === ((i >> 4) + (i & 15) & 255)));
  assert.throws(() => parseIntelHex([rows[0], rows[0]].join('\n')), /重叠/);
});
