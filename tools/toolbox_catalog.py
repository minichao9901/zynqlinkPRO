"""Offline control inventory; runtime describe remains authoritative for methods."""
from html.parser import HTMLParser


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.page = None
        self.sections = []
        self.items = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'section':
            self.sections.append(self.page)
            if a.get('id', '').startswith('tab-'):
                self.page = a['id'][4:]
        if tag in ('input', 'select', 'textarea', 'button') and a.get('id'):
            self.items.setdefault(self.page, []).append({
                'selector': '#' + a['id'], 'tag': tag, 'type': a.get('type'),
                'label': a.get('aria-label') or a.get('title') or a.get('placeholder'),
                'value': a.get('value'), 'disabled': 'disabled' in a})

    def handle_endtag(self, tag):
        if tag == 'section' and self.sections:
            self.page = self.sections.pop()


def full_catalog(root, catalog):
    parser = Controls()
    parser.feed((root / 'web/index.html').read_text(encoding='utf-8'))
    etm = Controls()
    etm.feed((root / 'etm-service/web/index.html').read_text(encoding='utf-8'))
    for page in catalog['pages']:
        page['controls'] = list(etm.items.get(None, [])) if page['id'] == 'etm' else parser.items.get(page['id'], [])
        page['runtimeMethods'] = f"page {page['id']} describe; page {page['id']} describe --target session/target/history"
    catalog['note'] = '静态控件清单；动态控件、可调用方法与当前禁用状态请读取 page P describe'
    return catalog
