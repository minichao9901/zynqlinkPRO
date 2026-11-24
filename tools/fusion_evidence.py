"""Offline data comparators for fusion acceptance captures."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def compare_stream(actual, expected):
    """Compare every byte and report the first differing offset."""
    offset=0
    with actual.open('rb') as a, expected.open('rb') as b:
        while True:
            left,right=a.read(1<<20),b.read(1<<20)
            if left!=right:
                mismatches=next((i for i,(x,y) in enumerate(zip(left,right)) if x!=y),min(len(left),len(right)))
                raise ValueError(f'Byte mismatch at offset {offset+mismatches}')
            if not left:
                if not offset:
                    raise ValueError('Empty captures are not evidence.')
                return offset
            offset+=len(left)


def compare_pattern(actual, pattern):
    data=pattern.read_bytes()
    if not data:
        raise ValueError('Empty reference pattern.')
    offset=0
    digest=hashlib.sha256()
    with actual.open('rb') as source:
        while block:=source.read(1<<20):
            begin=offset%len(data)
            repeated=(data*((begin+len(block)+len(data)-1)//len(data)))[begin:begin+len(block)]
            if block!=repeated:
                first=next(i for i,(x,y) in enumerate(zip(block,repeated)) if x!=y)
                raise ValueError(f'Pattern mismatch at offset {offset+first}')
            digest.update(block)
            offset+=len(block)
    if not offset:
        raise ValueError('Empty captures are not evidence.')
    return {'bytes':offset,'sha256':digest.hexdigest()}


def u32_sequence(path):
    count=0
    next_word=None
    first=None
    with path.open('rb') as stream:
        while chunk:=stream.read(65536):
            if len(chunk)%4:
                raise ValueError('RTT capture ends in a partial u32.')
            for word, in struct.iter_unpack('<I',chunk):
                if next_word is not None and next_word!=word:
                    raise ValueError(f'RTT word {count}: expected {next_word:#x}, got {word:#x}')
                if first is None:
                    first=word
                count+=1
                next_word=(word+1)&0xffffffff
    if not count:
        raise ValueError('Empty RTT capture.')
    return {'words':count,'first':first,'next':next_word,'bytes':count*4}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--actual',type=Path,required=True)
    ref=p.add_mutually_exclusive_group(required=True)
    ref.add_argument('--expected',type=Path)
    ref.add_argument('--pattern',type=Path)
    ref.add_argument('--u32-sequence',action='store_true')
    a=p.parse_args(argv)
    try:
        if a.expected:
            result={'bytes':compare_stream(a.actual,a.expected)}
        elif a.pattern:
            result=compare_pattern(a.actual,a.pattern)
        else:
            result=u32_sequence(a.actual)
        print(json.dumps(result,indent=2))
    except (OSError,ValueError) as error:
        p.exit(1,f'{error}\n')


if __name__=='__main__':
    main()
