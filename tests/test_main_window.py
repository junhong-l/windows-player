import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
resource_dir = str(Path(__file__).resolve().parents[1])
os.environ['PATH'] = resource_dir + os.pathsep + os.environ.get('PATH', '')
if os.name == 'nt':
    dll_directory = os.add_dll_directory(resource_dir)

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QStackedWidget, QWidget
from main_window import MainWindow
from player_core import PlayerCore


class PlaybackValueTests(unittest.TestCase):
    def test_volume_preserves_zero_and_defaults_only_when_missing(self):
        for value, expected in ((0, 0), (25.0, 25), (100, 100), (None, 100)):
            with self.subTest(value=value):
                core = SimpleNamespace(player=SimpleNamespace(volume=value))
                self.assertEqual(PlayerCore.volume.fget(core), expected)


class FullscreenTitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QMainWindow()
        central = QWidget()
        self.window.setCentralWidget(central)
        self.window.resize(1000, 600)
        self.window._is_fullscreen = True
        self.window._current_file = 'C:/videos/example.mp4'
        self.window.player = SimpleNamespace(is_paused=False, duration=120)
        self.window.stacked_widget = QStackedWidget(central)
        self.window.stacked_widget.addWidget(QWidget())
        self.window.stacked_widget.addWidget(QWidget())
        self.window.stacked_widget.setCurrentIndex(1)
        self.window.fullscreen_title = QLabel(central)
        self.window.fullscreen_title.hide()
        self.window.show()
        self.application.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def update_title(self, x, y, active=True):
        cursor = self.window.centralWidget().mapToGlobal(QPoint(x, y))
        with patch('main_window.QCursor.pos', return_value=cursor), patch.object(self.window, 'isActiveWindow', return_value=active):
            MainWindow._update_fullscreen_title(self.window)

    def test_playing_title_shows_only_in_top_left_corner(self):
        self.update_title(20, 20)
        self.assertFalse(self.window.fullscreen_title.isHidden())
        self.assertEqual(self.window.fullscreen_title.text(), 'example.mp4')
        for x, y in ((320, 20), (20, 50), (800, 20), (-1, 20)):
            self.update_title(x, y)
            self.assertTrue(self.window.fullscreen_title.isHidden())

    def test_paused_title_remains_visible_away_from_corner(self):
        self.window.player.is_paused = True
        self.update_title(800, 300)
        self.assertFalse(self.window.fullscreen_title.isHidden())
        self.window.player.is_paused = False
        self.update_title(800, 300)
        self.assertTrue(self.window.fullscreen_title.isHidden())

    def test_hover_does_not_show_outside_fullscreen_or_active_video(self):
        self.update_title(20, 20, active=False)
        self.assertTrue(self.window.fullscreen_title.isHidden())
        self.window._is_fullscreen = False
        self.update_title(20, 20)
        self.assertTrue(self.window.fullscreen_title.isHidden())
        self.window._is_fullscreen = True
        self.window.stacked_widget.setCurrentIndex(0)
        self.update_title(20, 20)
        self.assertTrue(self.window.fullscreen_title.isHidden())


if __name__ == '__main__':
    unittest.main()