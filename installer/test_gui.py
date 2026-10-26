"""Local synthetic Tk regressions. Never connect, download, or provision."""
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
from gui_theme import COLORS
from branding import icon_png,icon_ico
from setup_gui import App
import i18n


class PaletteTests(unittest.TestCase):
    def test_dashboard_accents(self):
        self.assertEqual([COLORS[n] for n in ('blue','purple','orange')],['#7EBAD2','#9B8BC1','#F6A453'])

    def test_original_icon_is_packaged_without_external_files(self):
        self.assertTrue(icon_png(32).startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(icon_ico()[:6],b'\x00\x00\x01\x00\x05\x00')


@unittest.skipIf(os.name!='nt' and not os.environ.get('DISPLAY'),'Tk display unavailable')
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.network=patch('setup_gui.Runner');self.runner=self.network.start()
        self.download=patch('setup_gui.windows_client.download');self.downloader=self.download.start()
        self.app=App('ru',True,'direct');self.app.root.withdraw()

    def tearDown(self):
        self.app.root.destroy();self.runner.assert_not_called();self.downloader.assert_not_called()
        self.network.stop();self.download.stop();i18n.set_language('ru')

    def widgets(self,parent=None):
        for child in (parent or self.app.root).winfo_children():
            yield child;yield from self.widgets(child)

    def test_languages_and_modes(self):
        for lang in ('ru','en'):
            self.app.lang.set('English' if lang=='en' else 'Русский');self.app.change_language()
            for mode in ('direct','cascade'):
                self.app.mode.set(mode);self.app.render();self.app.root.update_idletasks()
                self.assertEqual(len(self.app.tabs.tabs()),2)
                self.assertIn('DEMO',self.app.root.title())
                self.assertTrue(self.app.start_button.instate(['disabled']))

    def test_auth_switch_keeps_secret_in_memory_and_masks(self):
        node=self.app.foreign;node.password.set('SYNTHETIC_SECRET');node.passphrase.set('SYNTHETIC_KEY_SECRET')
        node.key.set('synthetic-private-key')
        for method in ('key','password','key'):
            node.auth.set(method);node.render_auth()
            for entry in self.widgets(node.auth_frame):
                if isinstance(entry,ttk.Entry) and str(entry.cget('textvariable')) in (str(node.password),str(node.passphrase)):
                    self.assertEqual(entry.cget('show'),'●')
        self.assertEqual(node.password.get(),'SYNTHETIC_SECRET');self.assertEqual(node.passphrase.get(),'SYNTHETIC_KEY_SECRET')

    def test_rerender_preserves_values_and_does_not_accept_terms(self):
        self.app.foreign.password.set('SYNTHETIC_SECRET');self.app.vpn_port.set('40000')
        self.app.mode.set('cascade');self.app.advanced.set(True);self.app.render()
        self.app.lang.set('English');self.app.change_language()
        self.assertEqual(self.app.foreign.password.get(),'SYNTHETIC_SECRET')
        self.assertEqual(self.app.vpn_port.get(),'40000');self.assertFalse(self.app.terms.get())
        self.assertFalse(self.app.running)

    def test_demo_handlers_cannot_provision_or_download(self):
        self.app.start();self.app.install_client();self.assertFalse(self.app.running);self.assertFalse(self.app.client_busy)

    def test_busy_state_disables_setup_controls(self):
        self.app.running=True;self.app.busy(True)
        self.assertEqual(str(self.app.langbox.cget('state')),'disabled')
        self.assertTrue(self.app.start_button.instate(['disabled']));self.assertTrue(self.app.cancel_button.instate(['!disabled']))
        self.app.running=False;self.app.busy(False)

    def test_small_window_footer_and_scroll_region(self):
        self.app.root.deiconify();self.app.root.geometry('920x680');self.app.mode.set('cascade')
        self.app.foreign.auth.set('key');self.app.entry.auth.set('key');self.app.advanced.set(True);self.app.render()
        self.app.root.update()
        for button in (self.app.start_button,self.app.client_button,self.app.cancel_button):
            self.assertGreater(button.winfo_width(),30)
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),self.app.root.winfo_rootx()+self.app.root.winfo_width())
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),self.app.root.winfo_rooty()+self.app.root.winfo_height())
        self.assertGreater(float(self.app.form_canvas.cget('scrollregion').split()[3]),self.app.form_canvas.winfo_height())
        self.app.form_canvas.yview_moveto(1);self.app.root.update_idletasks()
        self.assertAlmostEqual(self.app.form_canvas.yview()[1],1.,places=2)

    def test_flat_theme_and_readable_log(self):
        self.assertIn('Dashboard.card',str(self.app.theme.layout('Card.TFrame')))
        self.assertNotIn('Button.border',str(self.app.theme.layout('TButton')))
        self.assertEqual(self.app.logbox.cget('state'),'disabled')
        self.assertIn('подтверждения',self.app.logbox.get('1.0','end'))
        # A misplaced Tcl list delimiter used to produce a vertical stripe.
        image=self.app.root.dashboard_images[0]
        center=image.width()//2
        self.assertEqual(image.get(center,center),(31,31,31))
        self.assertGreaterEqual(image.width()-2*15,64)
        self.assertLess(self.app.start_button.winfo_reqheight(),70)


if __name__=='__main__':unittest.main()
