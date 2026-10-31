"""Application entry profile, shared with the imported superlinkPRO Trace CLI.

Low-level decoder defaults remain available for reference tests. Product entry
points explicitly select the same native profile as the portable application.
"""
import os

KEYS = ('ETM_STORE_WRITE', 'ETM_STORE_ENGINE', 'ETM_DECODE_ENGINE',
        'ETM_NATIVE_FORMAT', 'ETM_STORE_ENGINE_FALLBACK', 'ETM_EXPORT_ENGINE',
        'ETM_QUERY_ENGINE', 'ETM_PREPARE_CACHE')


def current_profile():
    settings = {key: os.environ.get(key) for key in KEYS}
    native = (settings['ETM_STORE_WRITE'] == '1' and settings['ETM_STORE_ENGINE'] == 'native'
              and settings['ETM_NATIVE_FORMAT'] == 'binary'
              and settings['ETM_STORE_ENGINE_FALLBACK'] == '0'
              and settings['ETM_DECODE_ENGINE'] == 'fast'
              and settings['ETM_EXPORT_ENGINE'] == 'native'
              and settings['ETM_QUERY_ENGINE'] == 'native')
    return dict(name='native' if native else 'custom', settings=settings,
                pipeline='OpenCSD binary -> C++ storebuild -> numeric query index',
                perInstructionJsonl=False if native else None)


def activate_native_profile():
    # One policy source: do not copy flags that can drift from superlinkPRO.
    from trace_cli import engine_environment
    engine_environment()
    return current_profile()
