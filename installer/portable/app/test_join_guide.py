"""Public manual-import screenshots; never create/download a real profile."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import struct
import tempfile
import unittest

from panel import create_app

ROOT=Path(__file__).parent/'static'
IMAGES={'amnezia-add-key.png':'b832bb8bda0b9be8604424e1702991378804ff85b7dd9435a52f616f7f1c063a',
        'amnezia-paste-key.png':'67742294337769a419f2b70ee49657b7613a170199c66d91a41c59366ab807da'}


class ImportGuideTests(unittest.TestCase):
    def test_original_screenshots_in_click_order_with_accessible_dimensions(self):
        class Images(HTMLParser):
            def __init__(self):super().__init__();self.images=[]
            def handle_starttag(self,tag,attrs):
                if tag=='img' and 'amnezia-' in dict(attrs).get('src',''):self.images.append(dict(attrs))
        html=(ROOT/'join.html').read_text(encoding='utf-8');parser=Images();parser.feed(html)
        self.assertEqual([a['src'] for a in parser.images],['/static/'+name for name in IMAGES])
        for image,(name,expected) in zip(parser.images,IMAGES.items()):
            payload=(ROOT/name).read_bytes();self.assertEqual(hashlib.sha256(payload).hexdigest(),expected)
            self.assertEqual(payload[:8],b'\x89PNG\r\n\x1a\n')
            self.assertEqual((int(image['width']),int(image['height'])),struct.unpack('>II',payload[16:24]))
            self.assertTrue(image['alt']);self.assertEqual(image['loading'],'lazy')
        self.assertIn('нажмите «Скопировать ключ»',html)
        self.assertIn('нажмите «+»',html);self.assertIn('нажмите «Вставить»',html)
        self.assertIn('id="import-app"',html);self.assertIn('id="copy"',html)

    def test_screenshots_and_guide_are_public_without_profile_issuance(self):
        with tempfile.TemporaryDirectory() as temp:
            app=create_app({'DATA_DIR':temp,'COLLECTOR':False});client=app.test_client()
            for path in ('/',)+tuple('/static/'+name for name in IMAGES):
                response=client.get(path);self.assertEqual(response.status_code,200)
                if path!='/':
                    self.assertEqual(response.mimetype,'image/png')
                    self.assertEqual(response.data,(ROOT/path.split('/')[-1]).read_bytes())
                response.close()
            with app.extensions['panel_db']() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM devices').fetchone()[0],0)

    def test_guide_styling_is_scoped_and_keeps_original_image_proportions(self):
        css=(ROOT/'style.css').read_text(encoding='utf-8')
        rule=css.split('.key-import-guide img{',1)[1].split('}',1)[0]
        self.assertIn('width:100%',rule);self.assertIn('height:auto',rule)
        self.assertIn('.key-import-guide figure{margin:0;min-width:0}',css)


if __name__=='__main__':unittest.main()
