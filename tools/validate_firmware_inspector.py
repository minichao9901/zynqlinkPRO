"""Offline Web acceptance: file inspection and saved-record reports; no probe actions."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from validate_f103_main_web import Web, ROOT
from toolbox import pack_file


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--record',help='Existing flight record ID in this isolated workbench')
    a=p.parse_args();w=Web(SimpleNamespace(runtime=a.runtime,artifacts=a.out,case_timeout=60))
    def text(selector):return w.page('flash','read',selector=selector)['text']
    def click(selector):w.page('flash','click',selector=selector)
    def load(path):
        w.page('flash','upload',selector='@file:view._fileInput',files=[pack_file(path)])
        w.wait('flash','#f-byte-info',path.name)
    w.page('flash','show');w.page('flash','describe')
    binfile=a.out/'pattern.bin';binfile.write_bytes(bytes(range(256))*4+b'X')
    load(binfile);assert '00 01 02 03' in text('#f-byte-content')
    click('#f-byte-next');assert text('#f-byte-page').startswith('513–1024')
    click('#f-byte-next');assert text('#f-byte-page').startswith('1025–1025')
    w.set('flash','#f-base','0x20000000');w.wait('flash','#f-byte-content','0x20000000')
    w.set('flash','#f-byte-address','0x20000400');click('#f-byte-go');assert '58 ' in text('#f-byte-content')
    click('#f-tab-elf');assert 'BIN / HEX' in text('#f-elf-note')
    h=a.out/'sparse.hex';h.write_text(':020000040800F2\n:0400000001020304F2\n:0430000005060708B2\n:00000001FF')
    load(h);assert '01 02 03 04' in text('#f-byte-content')
    w.set('flash','#f-byte-address','0x08003000');click('#f-byte-go');assert '05 06 07 08' in text('#f-byte-content')
    w.set('flash','#f-byte-address','0x08001000');click('#f-byte-go');assert '没有文件数据' in text('#f-byte-page')
    w.set('flash','#f-byte-source','raw');assert '3A 30 32' in text('#f-byte-content')
    elf=ROOT/'prebuilt/golden/f103ze-cdc48.elf';load(elf)
    click('#f-tab-elf');assert 'ARM' in text('#f-elf-content')
    w.set('flash','#f-elf-view','programs');assert 'LOAD' in text('#f-elf-content')
    w.set('flash','#f-elf-view','sections');assert '.text' in text('#f-elf-content')
    w.set('flash','#f-elf-view','symbols');click('#f-elf-next');assert text('#f-elf-page').startswith('101–')
    w.set('flash','#f-elf-search','main');w.wait('flash','#f-elf-page','1–');assert 'main' in text('#f-elf-content')
    broken=a.out/'truncated.elf';broken.write_bytes(elf.read_bytes()[:100]);load(broken)
    assert '无法生成烧录映像' in text('#f-byte-info');click('#f-tab-elf');assert '解析失败' in text('#f-elf-note')
    load(binfile);click('#f-tab-elf');assert 'BIN / HEX' in text('#f-elf-note')
    assert not text('#f-elf-content').strip(),'stale ELF results after BIN'
    load(elf);click('#f-tab-elf');w.set('flash','#f-elf-view','sections')
    result=dict(passed=True,hardwareAccess=False,cases=['BIN paging/base/jump','sparse HEX and hole','raw file bytes','ELF header/programs/sections/symbols/search/paging','truncated ELF rejected','ELF-to-BIN stale view cleared'])
    if a.record:
        w.page('etm','show');w.page('etm','describe',target='view')
        w.invoke('etm','openRecord',a.record)
        w.wait('etm','#summary-content','处理性能 Profile')
        report=w.page('etm','read',selector='#summary-content')['text']
        for expected in ['手动','物理覆盖旧历史','帧对齐移除','未知']:
            assert expected in report,expected
        assert 'SWD 时钟回读' not in report and 'LA 毛刺滤波快照' not in report
        w.page('etm','click',selector='#toggle-summary')
        controls=w.page('etm','describe',target='view')['controls']
        profile=next(c['selector'] for c in controls if c.get('text')=='Profile')
        w.page('etm','click',selector=profile)
        report=w.page('etm','read',selector='#summary-content')['text']
        for expected in ['USB 下载','原生建库','不相加']:assert expected in report,expected
        result['flightReport']=True
    (a.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
