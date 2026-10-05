import asyncio
import logging
import os
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from xml.etree import ElementTree

from aiohttp import ClientSession, web
from async_upnp_client.aiohttp import AiohttpRequester
from async_upnp_client.client_factory import UpnpFactory
from async_upnp_client.const import HttpResponse
from async_upnp_client.profiles.dlna import DmrDevice

from casting import CastDevice, CastManager, MediaServer, normalize_renderer_response, search_devices, prepare_cast_media, video_encoder_args, probe_video_encoder, cast_speed_filters


class VideoEncoderTests(unittest.IsolatedAsyncioTestCase):
    async def test_speed_filters_preserve_pitch_and_chain_three_times_speed(self):
        self.assertEqual(cast_speed_filters(1), ('', []))
        video, audio = cast_speed_filters(3)
        self.assertIn('setpts=(PTS-STARTPTS)/3', video)
        self.assertEqual(audio, ['-af', 'asetpts=PTS-STARTPTS,atempo=2,atempo=1.5'])
        self.assertIn('atempo=0.5', cast_speed_filters(0.5)[1][1])
        for speed in (0, 4, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                cast_speed_filters(speed)

    async def test_gpu_options_do_not_reuse_cpu_presets(self):
        expected = {'nvenc': 'h264_nvenc', 'amf': 'h264_amf', 'qsv': 'h264_qsv'}
        for encoder, codec in expected.items():
            arguments = video_encoder_args(encoder, True)
            self.assertEqual(arguments[arguments.index('-c:v') + 1], codec)
            self.assertNotIn('ultrafast', arguments)
            self.assertNotIn('zerolatency', arguments)
            self.assertEqual(arguments[arguments.index('-bf') + 1], '0')
            self.assertEqual(arguments[arguments.index('-profile:v') + 1],
                             'constrained_baseline' if encoder == 'amf' else 'baseline')

    async def test_cpu_options_preserve_existing_profiles(self):
        self.assertIn('ultrafast', video_encoder_args('cpu', True))
        self.assertIn('veryfast', video_encoder_args('cpu', False))
        with self.assertRaises(ValueError):
            video_encoder_args('unknown', True)

    async def test_probe_requires_successful_encoding_not_just_codec_name(self):
        for returncode, available in ((0, True), (1, False)):
            process = Mock(returncode=returncode, communicate=AsyncMock(return_value=(b'', b'driver status')))
            with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', new_callable=AsyncMock, return_value=process):
                self.assertEqual(await probe_video_encoder('nvenc'), available)

    async def test_probe_timeout_reaps_process_and_returns_unavailable(self):
        process = Mock(returncode=None, communicate=AsyncMock(side_effect=[TimeoutError(), (b'', b'')]))
        with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', new_callable=AsyncMock, return_value=process):
            self.assertFalse(await probe_video_encoder('nvenc'))
        process.kill.assert_called_once()
        self.assertEqual(process.communicate.await_count, 2)

    async def test_probe_cancellation_reaps_process_and_propagates(self):
        process = Mock(returncode=None, communicate=AsyncMock(side_effect=[asyncio.CancelledError(), (b'', b'')]))
        with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', new_callable=AsyncMock, return_value=process):
            with self.assertRaises(asyncio.CancelledError):
                await probe_video_encoder('amf')
        process.kill.assert_called_once()
        self.assertEqual(process.communicate.await_count, 2)


class CastDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt6.QtWidgets import QApplication
        cls.application = QApplication.instance() or QApplication([])

    def test_encoder_choices_filter_unavailable_devices_and_preserve_selection(self):
        from cast_dialog import CastDialog
        manager = Mock(busy=False, connected=False)
        dialog = CastDialog(manager, lambda: ('', 0))
        try:
            dialog._on_encoders(['cpu', 'nvenc', 'amf'])
            self.assertEqual([dialog.encoder_combo.itemData(index) for index in range(dialog.encoder_combo.count())],
                             ['auto', 'nvenc', 'amf', 'cpu'])
            dialog.encoder_combo.setCurrentIndex(dialog.encoder_combo.findData('amf'))
            dialog._on_encoders(['cpu', 'nvenc', 'amf'])
            self.assertEqual(dialog.encoder_combo.currentData(), 'amf')
            dialog.quality_combo.setCurrentIndex(dialog.quality_combo.findData(None))
            self.assertFalse(dialog.encoder_combo.isEnabled())
            self.assertFalse(dialog.speed_combo.isEnabled())
            self.assertEqual(dialog.speed_combo.currentData(), 1)
        finally:
            dialog._volume_timer.stop()
            dialog.deleteLater()

    def test_start_passes_encoder_and_duration_to_manager(self):
        from cast_dialog import CastDialog
        manager = Mock(busy=False, connected=False)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'video.mp4'
            path.write_bytes(b'video')
            dialog = CastDialog(manager, lambda: (str(path), 45, 120))
            try:
                dialog._on_devices([CastDevice('TV', 'http://192.168.1.2/description.xml', '192.168.1.2', 'uuid:tv')])
                dialog._on_encoders(['cpu', 'nvenc'])
                dialog.encoder_combo.setCurrentIndex(dialog.encoder_combo.findData('nvenc'))
                dialog.quality_combo.setCurrentIndex(dialog.quality_combo.findData(1440))
                dialog.speed_combo.setCurrentIndex(dialog.speed_combo.findData(1.5))
                dialog._start()
                self.assertEqual(manager.start.call_args.kwargs['encoder'], 'nvenc')
                self.assertEqual(manager.start.call_args.kwargs['duration'], 120)
                self.assertEqual(manager.start.call_args.kwargs['resolution'], 1440)
                self.assertEqual(manager.start.call_args.kwargs['speed'], 1.5)
            finally:
                dialog._volume_timer.stop()
                dialog.deleteLater()


    def test_status_is_not_periodically_polled_and_manual_sync_is_available(self):
        from cast_dialog import CastDialog
        manager = Mock(busy=False, connected=False)
        dialog = CastDialog(manager, lambda: ('', 0))
        try:
            self.assertFalse(hasattr(dialog, '_poll_timer'))
            manager.connected = True
            dialog._refresh_controls()
            self.assertTrue(dialog.sync_btn.isEnabled())
            dialog.sync_btn.click()
            manager.update.assert_called_once()
        finally:
            dialog._volume_timer.stop()
            dialog.deleteLater()

    def test_rate_display_updates_from_local_snapshot_and_resets_on_stop(self):
        from cast_dialog import CastDialog
        manager = Mock(busy=False, connected=False)
        dialog = CastDialog(manager, lambda: ('', 0))
        try:
            dialog._on_state(dict(position=30, duration=120, volume=None, state='PLAYING', transfer_mbps=12.345))
            self.assertEqual(dialog.rate_label.text(), "推送 12.35 Mbps")
            manager.update.assert_not_called()
            dialog._on_stopped({})
            self.assertEqual(dialog.rate_label.text(), "推送 0.00 Mbps")
        finally:
            dialog._volume_timer.stop()
            dialog.deleteLater()

    def test_connected_speed_control_sends_command_and_state_sync_does_not(self):
        from cast_dialog import CastDialog
        manager = Mock(busy=False, connected=False)
        dialog = CastDialog(manager, lambda: ('', 0))
        try:
            manager.connected = True
            dialog._on_state(dict(position=30, duration=120, volume=None, state='PLAYING', speed=1.5, can_speed=True))
            manager.command.assert_not_called()
            self.assertTrue(dialog.speed_combo.isEnabled())
            self.assertEqual(dialog.speed_combo.currentData(), 1.5)
            dialog.speed_combo.setCurrentIndex(dialog.speed_combo.findData(2))
            manager.command.assert_called_once_with('speed', 2)
            dialog._on_state(dict(position=30, duration=120, volume=None, state='PLAYING', speed=2, can_speed=False))
            self.assertFalse(dialog.speed_combo.isEnabled())
        finally:
            dialog._volume_timer.stop()
            dialog.deleteLater()


class CastPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_raw_mode_does_not_invoke_ffmpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.mp4'
            path.write_bytes(b'source')
            with patch('casting.ffmpeg_executable') as executable:
                result = await prepare_cast_media(str(path), None, Mock())
            self.assertEqual(Path(result), path)
            executable.assert_not_called()

    async def test_compatible_mode_encodes_and_reuses_complete_cache(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            path = Path(directory) / 'source.mp4'
            path.write_bytes(b'original HEVC')
            process = Mock(returncode=0, wait=AsyncMock(return_value=0))
            process.stdout = asyncio.StreamReader()
            process.stdout.feed_data(b'out_time=00:00:01.00\nprogress=end\n')
            process.stdout.feed_eof()
            process.stderr.read = AsyncMock(return_value=b'')

            async def encode(*arguments, **kwargs):
                Path(arguments[-1]).write_bytes(b'compatible H264')
                return process

            progress = Mock()
            with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', side_effect=encode) as spawn:
                result = await prepare_cast_media(str(path), 720, progress)
                cached = await prepare_cast_media(str(path), 720, progress)
            self.assertEqual(result, cached)
            self.assertEqual(path.read_bytes(), b'original HEVC')
            self.assertEqual(Path(result).read_bytes(), b'compatible H264')
            spawn.assert_awaited_once()
            arguments = spawn.call_args.args
            self.assertEqual(arguments[arguments.index('-pix_fmt') + 1], 'yuv420p')
            self.assertEqual(arguments[arguments.index('-profile:v') + 1], 'baseline')
            self.assertEqual(arguments[arguments.index('-r') + 1], '30')
            self.assertEqual(arguments[arguments.index('-ac') + 1], '2')
            progress.assert_called_once()
            outputs = {result}
            with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', side_effect=encode) as spawn:
                for encoder, codec in (('nvenc', 'h264_nvenc'), ('amf', 'h264_amf')):
                    converted = await prepare_cast_media(str(path), 720, progress, encoder=encoder)
                    self.assertNotIn(converted, outputs)
                    outputs.add(converted)
                    arguments = spawn.call_args.args
                    self.assertEqual(arguments[arguments.index('-c:v') + 1], codec)
                    self.assertEqual(await prepare_cast_media(str(path), 720, progress, encoder=encoder), converted)
                self.assertEqual(spawn.await_count, 2)
            with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', side_effect=encode) as spawn:
                fast = await prepare_cast_media(str(path), 720, progress, speed=2)
                self.assertNotIn(fast, outputs)
                self.assertEqual(await prepare_cast_media(str(path), 720, progress, speed=2), fast)
                spawn.assert_awaited_once()
                arguments = spawn.call_args.args
                self.assertIn('setpts=(PTS-STARTPTS)/2', arguments[arguments.index('-vf') + 1])
                self.assertIn('atempo=2', arguments[arguments.index('-af') + 1])

    async def test_2k_conversion_uses_1440p_dimensions_and_level(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            path = Path(directory) / 'source.mp4'
            path.write_bytes(b'video')
            process = Mock(returncode=0, wait=AsyncMock(return_value=0))
            process.stdout = asyncio.StreamReader()
            process.stdout.feed_eof()
            process.stderr.read = AsyncMock(return_value=b'')

            async def encode(*arguments, **kwargs):
                Path(arguments[-1]).write_bytes(b'compatible H264')
                return process

            with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', side_effect=encode) as spawn:
                await prepare_cast_media(str(path), 1440, Mock())
            arguments = spawn.call_args.args
            self.assertIn('2560', arguments[arguments.index('-vf') + 1])
            self.assertIn('1440', arguments[arguments.index('-vf') + 1])
            self.assertEqual(arguments[arguments.index('-level:v') + 1], '5.0')
            self.assertEqual(arguments[arguments.index('-b:v') + 1], '8000k')

    async def test_failed_conversion_does_not_publish_partial_cache(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            path = Path(directory) / 'source.mp4'
            path.write_bytes(b'source')
            process = Mock(returncode=1, wait=AsyncMock(return_value=1))
            process.stdout = asyncio.StreamReader()
            process.stdout.feed_eof()
            process.stderr.read = AsyncMock(return_value=b'unsupported input')
            with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', return_value=process):
                with self.assertRaisesRegex(RuntimeError, 'unsupported input'):
                    await prepare_cast_media(str(path), 1080, Mock())
            self.assertEqual(list((Path(directory) / 'VideoPlayer' / 'cast-cache').iterdir()), [])


    async def test_cancelled_conversion_kills_encoder_and_removes_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            path = Path(directory) / 'source.mp4'
            path.write_bytes(b'source')
            ready = asyncio.Event()
            process = Mock(returncode=None, wait=AsyncMock(return_value=0))
            process.stdout = asyncio.StreamReader()
            process.stderr.read = AsyncMock(return_value=b'')

            async def encode(*arguments, **kwargs):
                Path(arguments[-1]).write_bytes(b'partial video')
                ready.set()
                return process

            with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', side_effect=encode):
                task = asyncio.create_task(prepare_cast_media(str(path), 720, Mock()))
                await ready.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            process.kill.assert_called_once()
            process.wait.assert_awaited_once()
            self.assertEqual(list((Path(directory) / 'VideoPlayer' / 'cast-cache').iterdir()), [])


class MediaServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'test video.mp4'
        self.path.write_bytes(b'0123456789')
        self.server = MediaServer()
        self.url = await self.server.start(str(self.path), '127.0.0.1')
        self.client = ClientSession()

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()
        self.directory.cleanup()

    async def test_get_and_head(self):
        async with self.client.get(self.url) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.read(), b'0123456789')
            self.assertEqual(response.headers['Content-Type'], 'video/mp4')
        self.assertEqual(self.server.bytes_sent, 10)
        async with self.client.head(self.url) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['Content-Length'], '10')
            self.assertEqual(await response.read(), b'')
        self.assertEqual(self.server.bytes_sent, 10)

    async def test_partial_and_suffix_reads(self):
        async with self.client.get(self.url, headers={'Range': 'bytes=2-5'}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers['Content-Range'], 'bytes 2-5/10')
            self.assertEqual(await response.read(), b'2345')
        async with self.client.get(self.url, headers={'Range': 'bytes=-3'}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(await response.read(), b'789')
        self.assertEqual(self.server.bytes_sent, 7)

    async def test_transfer_rate_uses_recent_payload_and_expires_when_idle(self):
        with patch('casting.time.monotonic', return_value=10):
            self.server._record_bytes(1_000_000)
            self.assertEqual(self.server.transfer_mbps, 8)
        with patch('casting.time.monotonic', return_value=10.5):
            self.server._record_bytes(500_000)
            self.assertEqual(self.server.transfer_mbps, 12)
        with patch('casting.time.monotonic', return_value=11):
            self.assertEqual(self.server.transfer_mbps, 4)
        with patch('casting.time.monotonic', return_value=11.5):
            self.assertEqual(self.server.transfer_mbps, 0)
        self.assertEqual(self.server.bytes_sent, 1_500_000)
        await self.server.close()
        self.assertEqual(self.server.bytes_sent, 0)
        self.assertEqual(self.server.transfer_mbps, 0)

    async def test_invalid_range(self):
        async with self.client.get(self.url, headers={'Range': 'bytes=20-'}) as response:
            self.assertEqual(response.status, 416)

    async def test_video_requests_are_counted_and_logged(self):
        with self.assertLogs('casting', level='INFO') as logs:
            async with self.client.get(self.url, headers={'Range': 'bytes=0-0'}) as response:
                await response.read()
        self.assertEqual(self.server.request_count, 1)
        self.assertTrue(any('DLNA video request' in line and 'bytes=0-0' in line for line in logs.output))

    async def test_only_random_video_route_is_exposed(self):
        origin = self.url.rsplit('/', 2)[0]
        for route in ('/', '/test%20video.mp4', '/missing/video.mp4', '/README.md'):
            async with self.client.get(origin + route) as response:
                self.assertEqual(response.status, 404)

    async def test_replacement_closes_previous_server(self):
        previous_url = self.url
        self.url = await self.server.start(str(self.path), '127.0.0.1')
        self.assertNotEqual(previous_url, self.url)
        async with self.client.get(self.url) as response:
            self.assertEqual(response.status, 200)

    async def test_missing_file_does_not_leave_listener(self):
        with self.assertRaises(FileNotFoundError):
            await self.server.start(str(self.path.parent / 'missing.mp4'), '127.0.0.1')
        self.assertIsNone(self.server.url)

    async def test_live_head_does_not_start_an_encoder(self):
        with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec') as spawn:
            self.url = await self.server.start(str(self.path), '127.0.0.1', 720)
            async with self.client.head(self.url) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers['Content-Type'], 'video/mpeg')
                self.assertEqual(response.headers['Accept-Ranges'], 'none')
                self.assertNotIn('Content-Length', response.headers)
        spawn.assert_not_called()
        self.assertEqual(self.server.bytes_sent, 0)

    async def test_live_bytes_are_sent_before_encoding_finishes_and_stop_kills_process(self):
        process = Mock(returncode=None, wait=AsyncMock(return_value=0), communicate=AsyncMock(return_value=(b'', b'')))
        process.stdout = asyncio.StreamReader()
        process.stdout.feed_data(b'\x47' + b'live TS' * 100)
        process.stderr.read = AsyncMock(return_value=b'')
        with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', new_callable=AsyncMock, return_value=process) as spawn:
            self.url = await self.server.start(str(self.path), '127.0.0.1', 720, 12)
            async with self.client.get(self.url, headers={'Range': 'bytes=0-'}) as response:
                first = await asyncio.wait_for(response.content.read(188), 1)
                self.assertEqual(response.status, 200)
                self.assertEqual(first[0], 0x47)
                self.assertEqual(self.server.bytes_sent, 701)
                process.wait.assert_not_awaited()
                await self.server.close()
        process.kill.assert_called_once()
        process.communicate.assert_awaited_once()
        self.assertFalse(self.server._processes)
        arguments = spawn.call_args.args
        self.assertEqual(arguments[arguments.index('-f') + 1], 'mpegts')
        self.assertEqual(arguments[arguments.index('-ss') + 1], '12')


    async def test_live_encoder_failure_is_reported_without_publishing_video(self):
        process = Mock(returncode=1, wait=AsyncMock(return_value=1), communicate=AsyncMock(return_value=(b'', b'')))
        process.stdout = asyncio.StreamReader()
        process.stdout.feed_eof()
        process.stderr.read = AsyncMock(return_value=b'encoder failed')
        with patch('casting.ffmpeg_executable', return_value='ffmpeg'), patch('casting.asyncio.create_subprocess_exec', new_callable=AsyncMock, return_value=process), self.assertLogs('casting', level='INFO'):
            self.url = await self.server.start(str(self.path), '127.0.0.1', 720)
            async with self.client.get(self.url) as response:
                self.assertEqual(response.status, 500)
                await response.read()
        self.assertIn('encoder failed', self.server.error)
        self.assertFalse(self.server.stream_started)
        self.assertFalse(self.server._processes)


class CastManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = CastManager()
        self.profile = Mock()
        self.manager._start_monitor = AsyncMock()
        for name in ('construct_play_media_metadata', 'async_set_transport_uri',
                     'async_wait_for_can_play', 'async_play', 'async_stop',
                     'async_seek_rel_time', 'async_seek_abs_time', 'async_pause',
                     'async_update', 'async_set_volume_level'):
            setattr(self.profile, name, AsyncMock())
        self.profile.construct_play_media_metadata.return_value = '<DIDL-Lite/>'
        self.profile.transport_state.value = 'PLAYING'
        self.profile.media_position = 12
        self.profile.media_duration = 100
        self.profile.volume_level = 0.5
        self.device = CastDevice('Test TV', 'http://192.168.1.2/device.xml', '192.168.1.2', 'uuid:test')
        self.manager._profiles[self.device.location] = self.profile
        self.manager._server = Mock(start=AsyncMock(return_value='http://192.168.1.3/video.mp4'), close=AsyncMock(), error=None, stream_started=True, transfer_mbps=0, bytes_sent=0)

    async def asyncTearDown(self):
        self.manager._renderer = None
        self.manager.close()
        self.assertFalse(self.manager._thread.is_alive())

    async def test_start_and_seek(self):
        with patch('casting.route_address', return_value='192.168.1.3'):
            await self.manager._start(self.device, 'test.mp4', 12)
        self.profile.async_set_transport_uri.assert_awaited_once()
        self.profile.async_play.assert_awaited_once()
        self.profile.async_seek_rel_time.assert_awaited_once()
        self.assertTrue(self.manager.connected)
        self.assertEqual(self.manager.snapshot()['position'], 12)

    async def test_compatible_cast_serves_converted_video_and_retains_original_identity(self):
        with patch('casting.route_address', return_value='192.168.1.3'), patch('casting.prepare_cast_media', new_callable=AsyncMock, return_value='compatible.mp4') as prepare:
            await self.manager._start(self.device, 'original.mkv', 0, 720, delivery='file')
        self.manager._server.start.assert_awaited_once_with('compatible.mp4', '192.168.1.3')
        self.assertEqual(self.manager.file_path, 'original.mkv')
        self.assertEqual(prepare.await_args.args[:2], ('original.mkv', 720))
        self.assertEqual(self.profile.construct_play_media_metadata.await_args.kwargs['override_mime_type'], 'video/mp4')

    async def test_conversion_failure_does_not_send_uri_play_or_stop(self):
        with patch('casting.prepare_cast_media', new_callable=AsyncMock, side_effect=RuntimeError('encoder failed')), self.assertLogs('casting', level='INFO'):
            with self.assertRaisesRegex(RuntimeError, 'encoder failed'):
                await self.manager._start(self.device, 'original.mp4', 0, 1080, delivery='file')
        self.assertFalse(self.manager.connected)
        self.profile.async_set_transport_uri.assert_not_awaited()
        self.profile.async_play.assert_not_awaited()
        self.profile.async_stop.assert_not_awaited()

    async def test_live_cast_does_not_wait_for_complete_conversion(self):
        with patch('casting.route_address', return_value='192.168.1.3'), patch('casting.prepare_cast_media', new_callable=AsyncMock) as prepare:
            await self.manager._start(self.device, 'original.mkv', 129, 720, duration=300)
        prepare.assert_not_awaited()
        self.manager._server.start.assert_awaited_once_with('original.mkv', '192.168.1.3', resolution=720, position=129, encoder='cpu', speed=1)
        self.profile.async_seek_rel_time.assert_not_awaited()
        self.assertEqual(self.manager.snapshot()['position'], 141)
        self.assertEqual(self.manager.snapshot()['duration'], 300)
        self.assertEqual(self.profile.construct_play_media_metadata.await_args.kwargs['override_mime_type'], 'video/mpeg')

    async def test_live_seek_restarts_stream_instead_of_using_remote_byte_seek(self):
        with patch('casting.route_address', return_value='192.168.1.3'):
            await self.manager._start(self.device, 'original.mkv', 0, 720, duration=300)
            self.profile.media_position = 0
            await self.manager._command('seek', 60)
        self.assertEqual(self.manager._server.start.await_args.kwargs['position'], 60)
        self.profile.async_seek_rel_time.assert_not_awaited()
        self.profile.async_stop.assert_awaited_once()
        self.assertEqual(self.profile.async_play.await_count, 2)
        self.assertEqual(self.manager.snapshot()['position'], 60)

    async def test_speed_change_restarts_from_original_timeline_and_preserves_gpu(self):
        with patch('casting.route_address', return_value='192.168.1.3'), patch.object(self.manager, '_available_encoders', new=AsyncMock(return_value=['cpu', 'nvenc'])):
            await self.manager._start(self.device, 'original.mkv', 60, 1440, duration=300, encoder='nvenc', speed=2)
            self.assertEqual(self.manager.snapshot()['position'], 84)
            self.assertEqual(self.manager.snapshot()['duration'], 300)
            self.assertTrue(self.manager.snapshot()['can_speed'])
            self.profile.async_play.side_effect = lambda: setattr(self.profile, 'media_position', 0)
            await self.manager._command('speed', 1.5)
        arguments = self.manager._server.start.await_args.kwargs
        self.assertEqual(arguments, dict(resolution=1440, position=84, encoder='nvenc', speed=1.5))
        self.assertEqual(self.manager.snapshot()['speed'], 1.5)
        self.assertEqual(self.manager.snapshot()['position'], 84)

    async def test_changing_speed_while_paused_reapplies_pause_after_rebuild(self):
        with patch('casting.route_address', return_value='192.168.1.3'):
            await self.manager._start(self.device, 'original.mkv', 60, 720, duration=300)
            self.profile.transport_state.value = 'PAUSED_PLAYBACK'
            await self.manager._command('speed', 2)
        self.profile.async_pause.assert_awaited_once()
        self.assertEqual(self.manager._server.start.await_args.kwargs['position'], 72)
        self.assertEqual(self.manager._server.start.await_args.kwargs['speed'], 2)

    async def test_speed_rebuild_failure_releases_session_and_encoder(self):
        with patch('casting.route_address', return_value='192.168.1.3'):
            await self.manager._start(self.device, 'original.mkv', 0, 720)
            self.manager._server.start.side_effect = RuntimeError('encoder failed')
            with self.assertLogs('casting', level='INFO'), self.assertRaises(RuntimeError):
                await self.manager._command('speed', 2)
        self.assertFalse(self.manager.connected)
        self.manager._server.close.assert_awaited_once()
        self.assertEqual(self.manager._playback_speed, 1)

    async def test_cached_speed_converts_seek_and_duration_to_original_timeline(self):
        with patch('casting.route_address', return_value='192.168.1.3'), patch('casting.prepare_cast_media', new_callable=AsyncMock, return_value='compatible.mp4') as prepare:
            await self.manager._start(self.device, 'original.mkv', 60, 720, delivery='file', speed=2)
        self.assertEqual(prepare.await_args.kwargs['speed'], 2)
        self.profile.async_seek_rel_time.assert_awaited_with(timedelta(seconds=30))
        self.assertEqual(self.manager.snapshot()['position'], 24)
        self.assertEqual(self.manager.snapshot()['duration'], 200)
        self.assertFalse(self.manager.snapshot()['can_speed'])

    async def test_progress_clock_tracks_speed_and_freezes_on_pause_notification(self):
        with patch('casting.route_address', return_value='192.168.1.3'):
            await self.manager._start(self.device, 'original.mkv', 60, 720, speed=2, duration=300)
        self.manager._event_profile = self.profile
        with patch('casting.time.monotonic', return_value=100):
            self.manager._reset_position_clock(from_receiver=True)
        with patch('casting.time.monotonic', return_value=103):
            self.assertEqual(self.manager.snapshot(estimate=True)['position'], 90)
            self.profile.transport_state.value = 'PAUSED_PLAYBACK'
            variable = Mock()
            variable.name = 'TransportState'
            self.manager._on_renderer_event(self.profile, Mock(service_id='AVTransport'), [variable])
        with patch('casting.time.monotonic', return_value=110):
            self.assertEqual(self.manager.snapshot(estimate=True)['position'], 90)
        self.manager._event_profile = None

    async def test_cancelled_subscription_preparation_closes_notify_and_media_servers(self):
        server = Mock(async_start_server=AsyncMock(), async_stop_server=AsyncMock())
        event_profile = Mock(async_subscribe_services=AsyncMock(side_effect=asyncio.CancelledError()),
                             async_unsubscribe_services=AsyncMock())
        self.manager._start_monitor = CastManager._start_monitor.__get__(self.manager)
        with patch('casting.route_address', return_value='127.0.0.1'), patch('casting.AiohttpNotifyServer', return_value=server), patch('casting.DmrDevice', return_value=event_profile):
            with self.assertRaises(asyncio.CancelledError):
                await self.manager._start(self.device, 'original.mkv', 0, 720)
        self.assertFalse(self.manager.connected)
        self.assertIsNone(self.manager._notify_server)
        self.assertIsNone(self.manager._monitor_task)
        server.async_stop_server.assert_awaited_once()
        event_profile.async_unsubscribe_services.assert_awaited_once()
        self.manager._server.close.assert_awaited_once()

    async def test_notification_wakes_monitor_without_querying_device(self):
        self.manager._event_profile = self.profile
        self.manager._state_wakeup = asyncio.Event()
        self.manager._on_renderer_event(self.profile, Mock(service_id='AVTransport'), [Mock()])
        self.assertTrue(self.manager._state_wakeup.is_set())
        self.profile.async_update.assert_not_awaited()
        self.manager._event_profile = None

    async def test_published_event_state_does_not_query_receiver(self):
        with patch('casting.route_address', return_value='192.168.1.3'):
            await self.manager._start(self.device, 'original.mkv', 0, 720)
        self.profile.async_update.reset_mock()
        self.profile.transport_state.value = 'PAUSED_PLAYBACK'
        received = []
        self.manager.sessionChanged.connect(received.append)
        await self.manager._publish_state()
        self.assertEqual(received[-1]['state'], 'PAUSED_PLAYBACK')
        self.profile.async_update.assert_not_awaited()

    async def test_live_seek_failure_releases_session(self):
        with patch('casting.route_address', return_value='192.168.1.3'), self.assertLogs('casting', level='INFO'):
            await self.manager._start(self.device, 'original.mkv', 0, 720)
            self.profile.async_set_transport_uri.side_effect = RuntimeError('receiver rejected stream')
            with self.assertRaises(RuntimeError):
                await self.manager._command('seek', 60)
        self.assertFalse(self.manager.connected)
        self.manager._server.close.assert_awaited_once()

    async def test_live_success_requires_bytes_to_have_been_sent(self):
        self.manager._server.stream_started = False
        started = []
        self.manager.started.connect(started.append)
        with patch('casting.route_address', return_value='192.168.1.3'):
            await self.manager._start(self.device, 'original.mkv', 0, 720)
        self.assertEqual(started, [])
        self.manager._server.stream_started = True
        await self.manager._update()
        self.assertEqual(len(started), 1)

    async def test_live_encoder_error_releases_session_and_stops_polling(self):
        with patch('casting.route_address', return_value='192.168.1.3'):
            await self.manager._start(self.device, 'original.mkv', 0, 720)
        self.manager._server.error = 'live encoder failed'
        with self.assertRaisesRegex(RuntimeError, 'live encoder failed'):
            await self.manager._update()
        self.assertFalse(self.manager.connected)
        self.assertFalse(self.manager.update())
        self.manager._server.close.assert_awaited_once()

    async def test_gpu_probe_results_are_cached_and_reemitted_on_reopen(self):
        received = []
        self.manager.encodersFound.connect(received.append)
        with patch('casting.probe_video_encoder', new_callable=AsyncMock, side_effect=[True, True, False]) as probe:
            self.assertEqual(await self.manager._available_encoders(), ['cpu', 'nvenc', 'amf'])
            self.assertEqual(await self.manager._available_encoders(), ['cpu', 'nvenc', 'amf'])
        self.assertEqual(probe.await_count, 3)
        self.assertEqual(len(received), 2)

    async def test_unavailable_gpu_fails_before_remote_play_or_media_service(self):
        with patch.object(self.manager, '_available_encoders', new=AsyncMock(return_value=['cpu'])):
            with self.assertRaises(RuntimeError):
                await self.manager._start(self.device, 'original.mkv', 0, 720, encoder='nvenc')
        self.profile.async_set_transport_uri.assert_not_awaited()
        self.profile.async_play.assert_not_awaited()
        self.manager._server.start.assert_not_awaited()

    async def test_auto_prefers_validated_gpu_and_falls_back_to_cpu(self):
        with patch.object(self.manager, '_available_encoders', new=AsyncMock(return_value=['cpu', 'amf', 'nvenc'])):
            self.assertEqual(await self.manager._select_encoder('auto'), 'nvenc')
            self.assertEqual(await self.manager._select_encoder('amf'), 'amf')
        with patch.object(self.manager, '_available_encoders', new=AsyncMock(return_value=['cpu'])):
            self.assertEqual(await self.manager._select_encoder('auto'), 'cpu')
            with self.assertRaises(RuntimeError):
                await self.manager._select_encoder('nvenc')

    async def test_gpu_selection_is_preserved_when_rebuilding_stream(self):
        with patch('casting.route_address', return_value='192.168.1.3'), patch.object(self.manager, '_available_encoders', new=AsyncMock(return_value=['cpu', 'nvenc'])):
            await self.manager._start(self.device, 'original.mkv', 0, 720, encoder='auto')
            self.assertEqual(self.manager._server.start.await_args.kwargs['encoder'], 'nvenc')
            await self.manager._command('seek', 60)
        self.assertEqual(self.manager._server.start.await_args.kwargs['encoder'], 'nvenc')

    async def test_cached_conversion_receives_selected_gpu(self):
        with patch('casting.route_address', return_value='192.168.1.3'), patch.object(self.manager, '_available_encoders', new=AsyncMock(return_value=['cpu', 'amf'])), patch('casting.prepare_cast_media', new_callable=AsyncMock, return_value='compatible.mp4') as prepare:
            await self.manager._start(self.device, 'original.mkv', 0, 720, delivery='file', encoder='amf')
        self.assertEqual(prepare.await_args.kwargs['encoder'], 'amf')

    async def test_start_failure_releases_server(self):
        self.profile.async_play.side_effect = RuntimeError('TV rejected file')
        with patch('casting.route_address', return_value='192.168.1.3'):
            with self.assertRaises(RuntimeError):
                await self.manager._start(self.device, 'test.mp4', 0)
        self.manager._server.close.assert_awaited_once()
        self.assertFalse(self.manager.connected)

    async def test_timeout_identifies_stage_and_logs_traceback(self):
        self.profile.async_set_transport_uri.side_effect = TimeoutError()
        with patch('casting.route_address', return_value='192.168.1.3'), self.assertLogs('casting', level='INFO') as logs:
            with self.assertRaisesRegex(RuntimeError, 'SetAVTransportURI'):
                await self.manager._start(self.device, 'test.mp4', 0)
        self.assertTrue(any(record.exc_info for record in logs.records))
        self.profile.async_play.assert_not_awaited()
        self.manager._server.close.assert_awaited_once()

    async def test_background_failure_reports_the_failed_stage(self):
        self.profile.async_set_transport_uri.side_effect = TimeoutError()
        errors = []
        self.manager.failed.connect(errors.append)
        with patch('casting.route_address', return_value='192.168.1.3'), self.assertLogs('casting', level='INFO'):
            await self.manager._execute(lambda: self.manager._start(self.device, 'test.mp4', 0))
        self.assertEqual(len(errors), 1)
        self.assertIn('SetAVTransportURI', errors[0])
        self.assertFalse(self.manager.busy)

    async def test_debug_switch_changes_library_verbosity_and_locates_log(self):
        loggers = [logging.getLogger(name) for name in ('casting', 'async_upnp_client', 'aiohttp')]
        previous_levels = [item.level for item in loggers]
        with tempfile.TemporaryDirectory() as directory:
            handler = logging.FileHandler(Path(directory) / 'crash.log', encoding='utf-8')
            try:
                with patch.object(logging.getLogger(), 'handlers', [handler]):
                    self.assertEqual(self.manager.log_path, handler.baseFilename)
                    self.manager.set_debug(True)
                    self.assertTrue(all(item.level == logging.DEBUG for item in loggers))
                    self.manager.set_debug(False)
                    self.assertTrue(all(item.level == logging.INFO for item in loggers))
            finally:
                handler.close()
                for item, level in zip(loggers, previous_levels):
                    item.setLevel(level)

    async def test_controls_and_stop(self):
        self.manager.device = self.device
        self.manager.file_path = 'test.mp4'
        self.manager._renderer = self.profile
        await self.manager._command('pause', None)
        self.profile.async_pause.assert_awaited_once()
        await self.manager._command('volume', 0.25)
        self.profile.async_set_volume_level.assert_awaited_once_with(0.25)
        await self.manager._command('stop', None)
        self.profile.async_stop.assert_awaited_once()
        self.manager._server.close.assert_awaited_once()
        self.assertFalse(self.manager.connected)

    async def test_rejected_playback_expires_without_retry_and_can_start_again(self):
        self.profile.transport_state.value = 'STOPPED'
        self.manager._server.request_count = 1
        started = []
        self.manager.started.connect(started.append)
        with patch('casting.route_address', return_value='192.168.1.3'):
            await self.manager._start(self.device, 'test.mp4', 12)
            self.assertEqual(started, [])
            self.profile.async_seek_rel_time.assert_not_awaited()
            self.manager._start_deadline = 0
            with self.assertRaises(RuntimeError):
                await self.manager._update()
            self.assertFalse(self.manager.connected)
            self.assertFalse(self.manager.update())
            self.profile.async_play.assert_awaited_once()
            self.profile.async_set_transport_uri.assert_awaited_once()
            self.manager._server.close.assert_awaited_once()
            self.profile.transport_state.value = 'PLAYING'
            await self.manager._start(self.device, 'test.mp4', 0)
        self.assertTrue(self.manager.connected)
        self.assertEqual(len(started), 1)
        self.assertEqual(self.profile.async_play.await_count, 2)

    async def test_finished_playback_releases_session_without_sending_stop(self):
        with patch('casting.route_address', return_value='192.168.1.3'):
            await self.manager._start(self.device, 'test.mp4', 0)
        self.profile.transport_state.value = 'STOPPED'
        await self.manager._update()
        self.assertFalse(self.manager.connected)
        self.profile.async_stop.assert_not_awaited()
        self.manager._server.close.assert_awaited_once()

    async def test_first_status_failure_does_not_leave_a_connected_session(self):
        self.profile.async_update.side_effect = TimeoutError()
        started = []
        self.manager.started.connect(started.append)
        with patch('casting.route_address', return_value='192.168.1.3'), self.assertLogs('casting', level='INFO'):
            with self.assertRaises(RuntimeError):
                await self.manager._start(self.device, 'test.mp4', 0)
        self.assertFalse(self.manager.connected)
        self.assertEqual(started, [])
        self.assertFalse(self.manager.update())
        self.manager._server.close.assert_awaited_once()
        self.profile.async_stop.assert_not_awaited()

    async def test_pending_status_request_cannot_exceed_start_deadline(self):
        self.manager.device = self.device
        self.manager.file_path = 'test.mp4'
        self.manager._renderer = self.profile
        self.manager._start_deadline = time.monotonic() + 0.01
        pending = asyncio.Event()

        async def blocked_status():
            await pending.wait()

        self.profile.async_update.side_effect = blocked_status
        with self.assertLogs('casting', level='INFO'), self.assertRaises(RuntimeError):
            await asyncio.wait_for(self.manager._update(), 1)
        self.assertFalse(self.manager.connected)
        self.assertFalse(self.manager.update())
        self.profile.async_play.assert_not_awaited()
        self.manager._server.close.assert_awaited_once()

    async def test_stop_failure_still_releases_server(self):
        self.manager.device = self.device
        self.manager._renderer = self.profile
        self.profile.async_stop.side_effect = RuntimeError('Offline')
        with self.assertRaises(RuntimeError):
            await self.manager._disconnect()
        self.assertFalse(self.manager.connected)
        self.manager._server.close.assert_awaited_once()

    async def test_discovery_filters_and_deduplicates_devices(self):
        async def search(callback, **kwargs):
            await callback({'location': self.device.location})
            await callback({'location': 'file:///secret'})
            await callback({'location': 'http://127.0.0.1/device.xml'})
        root = Mock()
        candidate = Mock(device_type='urn:schemas-upnp-org:device:MediaRenderer:1',
                         friendly_name='Test TV', udn='uuid:test')
        root.all_devices = [candidate]
        factory = Mock(async_create_device=AsyncMock(return_value=root))
        found = []
        self.manager.devicesFound.connect(found.append)
        with patch('casting.search_devices', side_effect=search), patch('casting.UpnpFactory', return_value=factory), patch('casting.DmrDevice', return_value=self.profile) as profile_type:
            profile_type.DEVICE_TYPES = ['urn:schemas-upnp-org:device:MediaRenderer:1']
            await self.manager._discover(['192.168.1.3', '192.168.1.4'])
        factory.async_create_device.assert_awaited_once_with(self.device.location)
        self.assertEqual(len(found[0]), 1)
        self.assertEqual(found[0][0].name, 'Test TV')

    async def test_manual_device_bypasses_ssdp_and_refresh_reuses_its_address(self):
        candidate = Mock(device_type='urn:schemas-upnp-org:device:MediaRenderer:1',
                         friendly_name='Test TV', udn='uuid:test')
        factory = Mock(async_create_device=AsyncMock(return_value=Mock(all_devices=[candidate])))
        found = []
        self.manager.devicesFound.connect(found.append)
        with patch('casting.search_devices', new_callable=AsyncMock) as search, patch('casting.UpnpFactory', return_value=factory), patch('casting.DmrDevice', return_value=self.profile) as profile_type:
            profile_type.DEVICE_TYPES = ['urn:schemas-upnp-org:device:MediaRenderer:1']
            await self.manager._discover([], self.device.location)
            search.assert_not_awaited()
            await self.manager._discover(['192.168.1.3'])
        self.assertEqual(len(found), 2)
        self.assertTrue(all(devices[0].location == self.device.location for devices in found))
        self.assertEqual(factory.async_create_device.await_count, 2)

    async def test_manual_device_rejects_non_lan_addresses_before_requesting(self):
        with patch('casting.UpnpFactory') as factory:
            for location in ('file:///secret', 'http://127.0.0.1/device.xml',
                             'http://8.8.8.8/device.xml', '', 'http://user:password@192.168.1.2/device.xml'):
                with self.subTest(location=location), self.assertRaises(ValueError):
                    await self.manager._discover([], location)
        factory.assert_not_called()

    async def test_manual_device_rejects_media_servers(self):
        root = Mock(all_devices=[Mock(device_type='urn:schemas-upnp-org:device:MediaServer:1')])
        factory = Mock(async_create_device=AsyncMock(return_value=root))
        with patch('casting.UpnpFactory', return_value=factory):
            with self.assertRaises(RuntimeError):
                await self.manager._discover([], self.device.location)

    async def test_cancelled_search_closes_listener(self):
        ready = asyncio.Event()
        listener = Mock(async_start=AsyncMock())
        targets = []

        def sent():
            targets.append(listener.search_target)
            ready.set()

        listener.async_search.side_effect = sent
        with patch('casting.SsdpSearchListener', return_value=listener):
            task = asyncio.create_task(search_devices(AsyncMock(), '192.168.1.3'))
            await ready.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        listener.async_stop.assert_called_once()
        self.assertEqual(targets, ['ssdp:all', 'upnp:rootdevice',
                                   'urn:schemas-upnp-org:device:MediaRenderer:1'])

    async def test_description_error_is_reported(self):
        async def search(callback, **kwargs):
            await callback({'location': self.device.location})

        factory = Mock(async_create_device=AsyncMock(side_effect=RuntimeError('Invalid device XML')))
        with patch('casting.search_devices', side_effect=search), patch('casting.UpnpFactory', return_value=factory):
            with self.assertRaisesRegex(RuntimeError, 'Invalid device XML'):
                await self.manager._discover(['192.168.1.3'])

    async def test_media_servers_are_not_cast_receivers(self):
        async def search(callback, **kwargs):
            await callback({'location': self.device.location})

        root = Mock(all_devices=[Mock(device_type='urn:schemas-upnp-org:device:MediaServer:1')])
        factory = Mock(async_create_device=AsyncMock(return_value=root))
        found = []
        self.manager.devicesFound.connect(found.append)
        with patch('casting.search_devices', side_effect=search), patch('casting.UpnpFactory', return_value=factory):
            await self.manager._discover(['192.168.1.3'])
        self.assertEqual(found, [[]])


class RendererResponseTests(unittest.TestCase):
    def setUp(self):
        self.action = Mock()
        self.action.name = 'GetCurrentTransportActions'
        self.action.service.service_type = 'urn:schemas-upnp-org:service:AVTransport:1'

    def response(self, payload, status=200):
        body = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                'xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><s:Body>'
                + payload + '</s:Body></s:Envelope>')
        return HttpResponse(status, {}, body)

    def test_only_known_misnamed_response_is_normalized(self):
        response = self.response('<u:SetRecordQualityMode><Actions>Play,Pause</Actions></u:SetRecordQualityMode>')
        normalized = normalize_renderer_response(self.action, response)
        self.assertIsNot(normalized, response)
        self.assertIn('GetCurrentTransportActionsResponse', normalized.body)
        self.action.name = 'Play'
        self.assertIs(normalize_renderer_response(self.action, response), response)

    def test_faults_and_non_success_responses_are_preserved(self):
        fault = self.response('<s:Fault><faultcode>s:Client</faultcode></s:Fault>')
        self.assertIs(normalize_renderer_response(self.action, fault), fault)
        failure = self.response('<u:SetRecordQualityMode><Actions>Play</Actions></u:SetRecordQualityMode>', 500)
        self.assertIs(normalize_renderer_response(self.action, failure), failure)

    def test_unknown_or_malformed_responses_are_preserved(self):
        for payload in ('<u:Unknown><Actions>Play</Actions></u:Unknown>',
                        '<u:SetRecordQualityMode><Actions>Play</Actions><Extra/></u:SetRecordQualityMode>',
                        '<u:SetRecordQualityMode>'):
            with self.subTest(payload=payload):
                response = self.response(payload)
                self.assertIs(normalize_renderer_response(self.action, response), response)


class RendererIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.video = Path(self.directory.name) / 'sample.mp4'
        self.video.write_bytes(b'0123456789')
        self.state = {'state': 'STOPPED', 'position': '00:00:00', 'volume': 50, 'uri': ''}
        self.legacy_transport_response = False
        self.reject_subscriptions = False
        self.subscriptions = {}
        self.calls = []
        self.services = {
            'avt': ('AVTransport', {
                'InstanceID': 'ui4', 'URI': 'uri', 'Metadata': 'string',
                'TransportPlaySpeed': 'string', 'TransportState': 'string',
                'TransportStatus': 'string', 'CurrentTrack': 'ui4',
                'CurrentTrackDuration': 'string', 'CurrentTrackMetaData': 'string',
                'CurrentTrackURI': 'uri', 'RelativeTimePosition': 'string',
                'AbsoluteTimePosition': 'string', 'RelativeCounterPosition': 'i4',
                'AbsoluteCounterPosition': 'i4', 'A_ARG_TYPE_SeekMode': 'string',
                'A_ARG_TYPE_SeekTarget': 'string', 'CurrentTransportActions': 'string',
                'LastChange': 'string',
            }, {
                'SetAVTransportURI': [('InstanceID', 'in', 'InstanceID'), ('CurrentURI', 'in', 'URI'), ('CurrentURIMetaData', 'in', 'Metadata')],
                'Play': [('InstanceID', 'in', 'InstanceID'), ('Speed', 'in', 'TransportPlaySpeed')],
                'Pause': [('InstanceID', 'in', 'InstanceID')],
                'Stop': [('InstanceID', 'in', 'InstanceID')],
                'Seek': [('InstanceID', 'in', 'InstanceID'), ('Unit', 'in', 'A_ARG_TYPE_SeekMode'), ('Target', 'in', 'A_ARG_TYPE_SeekTarget')],
                'GetTransportInfo': [('InstanceID', 'in', 'InstanceID'), ('CurrentTransportState', 'out', 'TransportState'), ('CurrentTransportStatus', 'out', 'TransportStatus'), ('CurrentSpeed', 'out', 'TransportPlaySpeed')],
                'GetPositionInfo': [('InstanceID', 'in', 'InstanceID'), ('Track', 'out', 'CurrentTrack'), ('TrackDuration', 'out', 'CurrentTrackDuration'), ('TrackMetaData', 'out', 'CurrentTrackMetaData'), ('TrackURI', 'out', 'CurrentTrackURI'), ('RelTime', 'out', 'RelativeTimePosition'), ('AbsTime', 'out', 'AbsoluteTimePosition'), ('RelCount', 'out', 'RelativeCounterPosition'), ('AbsCount', 'out', 'AbsoluteCounterPosition')],
                'GetCurrentTransportActions': [('InstanceID', 'in', 'InstanceID'), ('Actions', 'out', 'CurrentTransportActions')],
            }),
            'rc': ('RenderingControl', {'InstanceID': 'ui4', 'Channel': 'string', 'Volume': 'ui2'}, {
                'GetVolume': [('InstanceID', 'in', 'InstanceID'), ('Channel', 'in', 'Channel'), ('CurrentVolume', 'out', 'Volume')],
                'SetVolume': [('InstanceID', 'in', 'InstanceID'), ('Channel', 'in', 'Channel'), ('DesiredVolume', 'in', 'Volume')],
            }),
            'cm': ('ConnectionManager', {'SourceProtocolInfo': 'string', 'SinkProtocolInfo': 'string'}, {
                'GetProtocolInfo': [('Source', 'out', 'SourceProtocolInfo'), ('Sink', 'out', 'SinkProtocolInfo')],
            }),
        }
        app = web.Application()
        app.router.add_get('/device.xml', self._device)
        app.router.add_get('/{service}.xml', self._scpd)
        app.router.add_post('/control/{service}', self._soap)
        app.router.add_route('SUBSCRIBE', '/events/{service}', self._subscribe)
        app.router.add_route('UNSUBSCRIBE', '/events/{service}', self._subscribe)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, '127.0.0.1', 0).start()
        self.location = f'http://127.0.0.1:{self.runner.addresses[0][1]}/device.xml'
        factory = UpnpFactory(AiohttpRequester(timeout=2), non_strict=True,
                      on_post_call_action=normalize_renderer_response)
        device = await factory.async_create_device(self.location)
        self.profile = DmrDevice(device, None)
        self.manager = CastManager()
        self.manager._profiles[self.location] = self.profile
        self.device = CastDevice('Simulated TV', self.location, '127.0.0.1', 'uuid:simulated')

    async def asyncTearDown(self):
        await self.manager._disconnect()
        self.manager.close()
        await self.runner.cleanup()
        self.directory.cleanup()

    async def _device(self, request):
        root = ElementTree.Element('root', xmlns='urn:schemas-upnp-org:device-1-0')
        version = ElementTree.SubElement(root, 'specVersion')
        ElementTree.SubElement(version, 'major').text = '1'
        ElementTree.SubElement(version, 'minor').text = '0'
        device = ElementTree.SubElement(root, 'device')
        for name, value in {'deviceType': 'urn:schemas-upnp-org:device:MediaRenderer:1', 'friendlyName': 'Simulated TV', 'manufacturer': 'Test', 'modelName': 'Test', 'UDN': 'uuid:simulated'}.items():
            ElementTree.SubElement(device, name).text = value
        services = ElementTree.SubElement(device, 'serviceList')
        for key, (name, _, _) in self.services.items():
            service = ElementTree.SubElement(services, 'service')
            for field, value in {'serviceType': f'urn:schemas-upnp-org:service:{name}:1', 'serviceId': f'urn:upnp-org:serviceId:{name}', 'SCPDURL': f'/{key}.xml', 'controlURL': f'/control/{key}', 'eventSubURL': f'/events/{key}'}.items():
                ElementTree.SubElement(service, field).text = value
        return web.Response(body=ElementTree.tostring(root), content_type='text/xml')

    async def _scpd(self, request):
        _, variables, actions = self.services[request.match_info['service']]
        root = ElementTree.Element('scpd', xmlns='urn:schemas-upnp-org:service-1-0')
        version = ElementTree.SubElement(root, 'specVersion')
        ElementTree.SubElement(version, 'major').text = '1'
        ElementTree.SubElement(version, 'minor').text = '0'
        action_list = ElementTree.SubElement(root, 'actionList')
        for name, arguments in actions.items():
            action = ElementTree.SubElement(action_list, 'action')
            ElementTree.SubElement(action, 'name').text = name
            argument_list = ElementTree.SubElement(action, 'argumentList')
            for argument_name, direction, variable in arguments:
                argument = ElementTree.SubElement(argument_list, 'argument')
                for field, value in {'name': argument_name, 'direction': direction, 'relatedStateVariable': variable}.items():
                    ElementTree.SubElement(argument, field).text = value
        table = ElementTree.SubElement(root, 'serviceStateTable')
        for name, data_type in variables.items():
            variable = ElementTree.SubElement(table, 'stateVariable', sendEvents='yes' if name in ('LastChange', 'Volume') else 'no')
            ElementTree.SubElement(variable, 'name').text = name
            ElementTree.SubElement(variable, 'dataType').text = data_type
            if name == 'A_ARG_TYPE_SeekMode':
                allowed = ElementTree.SubElement(variable, 'allowedValueList')
                for mode in ('REL_TIME', 'ABS_TIME'):
                    ElementTree.SubElement(allowed, 'allowedValue').text = mode
            if name == 'Volume':
                allowed = ElementTree.SubElement(variable, 'allowedValueRange')
                ElementTree.SubElement(allowed, 'minimum').text = '0'
                ElementTree.SubElement(allowed, 'maximum').text = '100'
                ElementTree.SubElement(allowed, 'step').text = '1'
        return web.Response(body=ElementTree.tostring(root), content_type='text/xml')

    async def _subscribe(self, request):
        if self.reject_subscriptions:
            return web.Response(status=412)
        service = request.match_info['service']
        sid = request.headers.get('SID', 'uuid:simulated-' + service)
        if request.method == 'UNSUBSCRIBE':
            self.subscriptions.pop(sid, None)
        elif 'CALLBACK' in request.headers:
            self.subscriptions[sid] = (service, request.headers['CALLBACK'].strip('<>'))
        return web.Response(headers={'SID': sid, 'TIMEOUT': 'Second-1800'})

    async def _notify(self, service, values):
        properties = ElementTree.Element('{urn:schemas-upnp-org:event-1-0}propertyset')
        for name, value in values.items():
            prop = ElementTree.SubElement(properties, '{urn:schemas-upnp-org:event-1-0}property')
            ElementTree.SubElement(prop, name).text = value
        sid, (_, callback) = next((sid, value) for sid, value in self.subscriptions.items() if value[0] == service)
        async with ClientSession() as client:
            async with client.request('NOTIFY', callback, data=ElementTree.tostring(properties),
                                      headers={'SID': sid, 'NT': 'upnp:event', 'NTS': 'upnp:propchange', 'SEQ': '0'}) as response:
                self.assertEqual(response.status, 200)

    async def _soap(self, request):
        root = ElementTree.fromstring(await request.text())
        body = root.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
        action = list(body)[0]
        name = action.tag.rsplit('}', 1)[-1]
        arguments = {child.tag.rsplit('}', 1)[-1]: child.text for child in action}
        self.calls.append(name)
        output = {}
        if name == 'SetAVTransportURI':
            self.state['uri'] = arguments['CurrentURI']
        elif name in ('Play', 'Pause', 'Stop'):
            self.state['state'] = {'Play': 'PLAYING', 'Pause': 'PAUSED_PLAYBACK', 'Stop': 'STOPPED'}[name]
        elif name == 'Seek':
            self.state['position'] = arguments['Target']
        elif name == 'SetVolume':
            self.state['volume'] = int(arguments['DesiredVolume'])
        elif name == 'GetVolume':
            output = {'CurrentVolume': str(self.state['volume'])}
        elif name == 'GetProtocolInfo':
            output = {'Source': '', 'Sink': 'http-get:*:video/mp4:*'}
        elif name == 'GetCurrentTransportActions':
            output = {'Actions': 'Play,Pause,Stop,Seek'}
        elif name == 'GetTransportInfo':
            output = {'CurrentTransportState': self.state['state'], 'CurrentTransportStatus': 'OK', 'CurrentSpeed': '1'}
        elif name == 'GetPositionInfo':
            output = {'Track': '1', 'TrackDuration': '00:01:40', 'TrackMetaData': '', 'TrackURI': self.state['uri'], 'RelTime': self.state['position'], 'AbsTime': self.state['position'], 'RelCount': '0', 'AbsCount': '0'}
        envelope = ElementTree.Element('{http://schemas.xmlsoap.org/soap/envelope/}Envelope')
        response_body = ElementTree.SubElement(envelope, '{http://schemas.xmlsoap.org/soap/envelope/}Body')
        service_name = self.services[request.match_info['service']][0]
        response_name = 'SetRecordQualityMode' if self.legacy_transport_response and name == 'GetCurrentTransportActions' else name + 'Response'
        response = ElementTree.SubElement(response_body, f'{{urn:schemas-upnp-org:service:{service_name}:1}}{response_name}')
        for key, value in output.items():
            ElementTree.SubElement(response, key).text = value
        return web.Response(body=ElementTree.tostring(envelope), content_type='text/xml')

    async def test_real_upnp_library_and_video_transfer(self):
        await self.manager._start(self.device, str(self.video), 12)
        self.assertTrue(self.manager.connected)
        self.assertEqual(self.manager.snapshot()['state'], 'PLAYING')
        self.assertEqual(self.manager.snapshot()['position'], 12)
        self.assertEqual(self.manager.snapshot()['duration'], 100)
        async with ClientSession() as client:
            async with client.get(self.state['uri'], headers={'Range': 'bytes=2-5'}) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(await response.read(), b'2345')
        await self.manager._command('pause', None)
        self.assertEqual(self.manager.snapshot()['state'], 'PAUSED_PLAYBACK')
        await self.manager._command('volume', 0.25)
        self.assertEqual(self.state['volume'], 25)
        await self.manager._command('stop', None)
        self.assertEqual(self.state['state'], 'STOPPED')
        self.assertIsNone(self.manager._server.url)
        self.assertIn('SetAVTransportURI', self.calls)

    async def test_push_updates_pause_volume_and_stop_without_status_queries(self):
        await self.manager._start(self.device, str(self.video), 0)
        self.assertTrue(self.manager._events_enabled)
        self.assertEqual(len(self.subscriptions), 3)
        calls_before = list(self.calls)
        paused, volume_changed, stopped = asyncio.Event(), asyncio.Event(), asyncio.Event()

        def changed(state):
            if state['state'] == 'PAUSED_PLAYBACK':
                paused.set()
            if state['volume'] == 0.25:
                volume_changed.set()

        self.manager.sessionChanged.connect(changed)
        self.manager.stopped.connect(lambda state: stopped.set())
        await self._notify('avt', {'LastChange': '<Event xmlns="urn:schemas-upnp-org:metadata-1-0/AVT/"><InstanceID val="0"><TransportState val="PAUSED_PLAYBACK"/></InstanceID></Event>'})
        await asyncio.wait_for(paused.wait(), 2)
        await self._notify('rc', {'Volume': '25'})
        await asyncio.wait_for(volume_changed.wait(), 2)
        self.assertEqual(self.calls, calls_before)
        await self._notify('avt', {'LastChange': '<Event xmlns="urn:schemas-upnp-org:metadata-1-0/AVT/"><InstanceID val="0"><TransportState val="STOPPED"/></InstanceID></Event>'})
        await asyncio.wait_for(stopped.wait(), 2)
        self.assertFalse(self.manager.connected)
        self.assertFalse(self.subscriptions)
        self.assertIsNone(self.manager._notify_server)
        self.assertIsNone(self.manager._monitor_task)
        self.assertEqual(self.calls, calls_before)

    async def test_rejected_subscription_does_not_restore_periodic_polling(self):
        self.reject_subscriptions = True
        with self.assertLogs('casting', level='WARNING'):
            await self.manager._start(self.device, str(self.video), 0)
        self.assertEqual(self.manager.snapshot()['status_sync'], 'manual')
        calls_before = list(self.calls)
        observed = asyncio.Event()
        asyncio.get_running_loop().call_later(2.2, observed.set)
        await asyncio.wait_for(observed.wait(), 3)
        self.assertEqual(self.calls, calls_before)

    async def test_ugreen_misnamed_transport_actions_response(self):
        self.legacy_transport_response = True
        await self.manager._start(self.device, str(self.video), 12)
        self.assertTrue(self.manager.connected)
        self.assertEqual(self.manager.snapshot()['state'], 'PLAYING')
        self.assertEqual(self.manager.snapshot()['position'], 12)
        await self.manager._command('pause', None)
        self.assertEqual(self.manager.snapshot()['state'], 'PAUSED_PLAYBACK')


if __name__ == '__main__':
    unittest.main()