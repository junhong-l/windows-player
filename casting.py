import asyncio
import hashlib
import ipaddress
import logging
import mimetypes
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web
from async_upnp_client.aiohttp import AiohttpRequester, AiohttpNotifyServer
from async_upnp_client.client_factory import UpnpFactory
from async_upnp_client.const import HttpResponse
from async_upnp_client.profiles.dlna import DmrDevice, TransportState
from async_upnp_client.search import SsdpSearchListener
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QAbstractSocket, QNetworkInterface
from airplay_receiver import AirPlayReceiver, discover_airplay, inspect_airplay


logger = logging.getLogger(__name__)

CAST_VIDEO_PROFILES = {
    720: (1280, '2000k', '3.1'),
    1080: (1920, '4000k', '4.0'),
    1440: (2560, '8000k', '5.0'),
    2160: (3840, '16000k', '5.1'),
}


def ffmpeg_executable():
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except ImportError as error:
        raise RuntimeError('兼容投屏需要转码工具，请运行 python -m pip install imageio-ffmpeg') from error
    return get_ffmpeg_exe()


def video_encoder_args(encoder, realtime):
    if encoder == 'cpu':
        options = ['-c:v', 'libx264', '-preset', 'ultrafast' if realtime else 'veryfast']
        if realtime:
            options += ['-tune', 'zerolatency']
    elif encoder == 'nvenc':
        options = ['-c:v', 'h264_nvenc', '-preset', 'p4', '-tune', 'll', '-bf', '0']
    elif encoder == 'amf':
        options = ['-c:v', 'h264_amf', '-usage', 'lowlatency', '-quality', 'speed', '-bf', '0']
    elif encoder == 'qsv':
        options = ['-c:v', 'h264_qsv', '-preset', 'veryfast', '-bf', '0']
    else:
        raise ValueError('Unsupported video encoder')
    return options + ['-profile:v', 'constrained_baseline' if encoder == 'amf' else 'baseline']


async def probe_video_encoder(encoder):
    command = [
        ffmpeg_executable(), '-hide_banner', '-loglevel', 'error', '-nostdin',
        '-f', 'lavfi', '-i', 'color=c=black:s=1280x720:r=30', '-frames:v', '3',
        *video_encoder_args(encoder, True), '-pix_fmt', 'yuv420p', '-level:v', '3.1',
        '-f', 'null', '-',
    ]
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    try:
        _, errors = await asyncio.wait_for(process.communicate(), 8)
        available = process.returncode == 0
        logger.info('DLNA GPU encoder probe: encoder=%s available=%s detail=%s',
                    encoder, available, errors.decode('utf-8', errors='replace')[-500:])
        return available
    except BaseException as error:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.communicate()
        if isinstance(error, TimeoutError):
            logger.info('DLNA GPU encoder probe timed out: encoder=%s', encoder)
            return False
        raise


def cast_speed_filters(speed):
    if not 0.5 <= speed <= 3:
        raise ValueError('Playback speed must be between 0.5 and 3')
    if speed == 1:
        return '', []
    factors = []
    remaining = speed
    while remaining > 2:
        factors.append('atempo=2')
        remaining /= 2
    factors.append(f'atempo={remaining:g}')
    return f',setpts=(PTS-STARTPTS)/{speed:g}', ['-af', 'asetpts=PTS-STARTPTS,' + ','.join(factors)]


async def prepare_cast_media(file_path, resolution, progress, encoder='cpu', speed=1):
    video_speed, audio_speed = cast_speed_filters(speed)
    path = Path(file_path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Video must be a regular file')
    if resolution is None:
        if speed != 1:
            raise ValueError('Raw casting does not support playback speed')
        return str(path)
    if resolution not in CAST_VIDEO_PROFILES:
        raise ValueError('Unsupported casting resolution')
    options = video_encoder_args(encoder, False)
    source = path.stat()
    identity = f'h264-v1:{path}:{source.st_size}:{source.st_mtime_ns}:{resolution}'
    if encoder != 'cpu':
        identity += ':' + encoder
    if speed != 1:
        identity += f':speed={speed:g}'
    key = hashlib.sha256(identity.encode('utf-8')).hexdigest()
    cache = Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir())) / 'VideoPlayer' / 'cast-cache'
    cache.mkdir(parents=True, exist_ok=True)
    output = cache / f'{key}.mp4'
    if output.is_file() and output.stat().st_size > 0:
        logger.info('DLNA transcode cache hit: file=%s resolution=%s', output, resolution)
        return str(output)
    width, bitrate, level = CAST_VIDEO_PROFILES[resolution]
    filters = f'scale=w=min(iw\\,{width}):h=min(ih\\,{resolution}):force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1'
    filters += video_speed
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=cache) as directory:
        temporary = Path(directory) / 'video.mp4'
        command = [
            ffmpeg_executable(), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-threads', '4', '-i', str(path), '-map', '0:v:0', '-map', '0:a:0?', '-sn', '-dn',
            '-vf', filters, '-r', '30', *options, '-level:v', level, '-pix_fmt', 'yuv420p',
            '-b:v', bitrate, '-maxrate', bitrate, '-bufsize', '8000k', '-g', '60',
            *audio_speed, '-c:a', 'aac', '-b:a', '128k', '-ac', '2', '-ar', '48000',
            '-movflags', '+faststart', '-threads', '4', '-progress', 'pipe:1', '-nostats', str(temporary),
        ]
        logger.info('DLNA transcode begin: input=%s resolution=%s encoder=%s speed=%s output=%s', path, resolution, encoder, speed, output)
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        errors = asyncio.create_task(process.stderr.read())
        try:
            while line := await process.stdout.readline():
                name, _, value = line.decode('utf-8', errors='replace').strip().partition('=')
                if name == 'out_time':
                    progress(f'正在转码 {resolution}p：{value.split(".")[0]}')
            returncode = await process.wait()
            detail = (await errors).decode('utf-8', errors='replace')
            if returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError('兼容视频转码失败：' + (detail[-1500:] or f'FFmpeg exit {returncode}'))
            temporary.replace(output)
            logger.info('DLNA transcode complete: file=%s size=%s', output, output.stat().st_size)
            return str(output)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            errors.cancel()
            await asyncio.gather(errors, return_exceptions=True)
            raise


class MeteredFileResponse(web.FileResponse):
    def __init__(self, path, on_bytes, **kwargs):
        super().__init__(path, **kwargs)
        self._on_bytes = on_bytes

    async def _sendfile(self, request, fobj, offset, count):
        writer = await web.StreamResponse.prepare(self, request)
        assert writer is not None
        loop = asyncio.get_running_loop()
        chunk = await loop.run_in_executor(None, self._seek_and_read, fobj, offset, min(self._chunk_size, count))
        while chunk:
            await writer.write(chunk)
            self._on_bytes(len(chunk))
            count -= len(chunk)
            if count <= 0:
                break
            chunk = await loop.run_in_executor(None, fobj.read, min(self._chunk_size, count))
        await writer.drain()
        await self.write_eof()
        return writer


class MediaServer:
    def __init__(self):
        self._runner = None
        self.url = None
        self.request_count = 0
        self.error = None
        self.stream_started = False
        self.bytes_sent = 0
        self._transfer_samples = deque()
        self._requests = set()
        self._processes = set()
        self._hls_directory = None
        self._hls_task = None

    def _trim_transfer_samples(self, now):
        while self._transfer_samples and self._transfer_samples[0][0] <= now - 1:
            self._transfer_samples.popleft()

    def _record_bytes(self, size):
        now = time.monotonic()
        self.bytes_sent += size
        self._trim_transfer_samples(now)
        self._transfer_samples.append((now, size))

    @property
    def transfer_mbps(self):
        self._trim_transfer_samples(time.monotonic())
        return sum(size for _, size in self._transfer_samples) * 8 / 1_000_000

    async def start(self, file_path: str, address: str, resolution=None, position=0, encoder='cpu', speed=1, hls=False) -> str:
        await self.close()
        cast_speed_filters(speed)
        if resolution is None and speed != 1:
            raise ValueError('Raw casting does not support playback speed')
        path = Path(file_path).resolve(strict=True)
        if not path.is_file():
            raise ValueError("Video must be a regular file")
        if resolution is not None and resolution not in CAST_VIDEO_PROFILES:
            raise ValueError('Unsupported casting resolution')
        executable = ffmpeg_executable() if resolution is not None else None
        if resolution is not None:
            video_encoder_args(encoder, True)
        self.request_count = 0
        self.error = None
        self.stream_started = False
        if hls:
            if resolution is None:
                raise ValueError('HLS requires compatible video quality')
            return await self._start_hls(path, address, resolution, position, executable, encoder, speed)
        suffix = '.ts' if resolution is not None else path.suffix.lower()
        route = f"/{secrets.token_urlsafe(24)}/video{suffix}"
        mime_type = 'video/mpeg' if resolution is not None else (mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        async def serve(request):
            self.request_count += 1
            logger.info('DLNA video request: method=%s remote=%s range=%s',
                        request.method, request.remote, request.headers.get('Range', '-'))
            if resolution is not None:
                return await self._serve_stream(request, path, resolution, position, executable, encoder, speed)
            return MeteredFileResponse(path, self._record_bytes, headers={
                'Content-Type': mime_type,
                'Cache-Control': 'no-store',
                'transferMode.dlna.org': 'Streaming',
                'contentFeatures.dlna.org': 'DLNA.ORG_OP=01;DLNA.ORG_CI=0',
            })

        app = web.Application()
        app.router.add_get(route, serve)
        runner = web.AppRunner(app, access_log=logging.getLogger('casting.http'), shutdown_timeout=1)
        try:
            await runner.setup()
            site = web.TCPSite(runner, address, 0)
            await site.start()
            port = runner.addresses[0][1]
            self.url = f'http://{address}:{port}{route}'
            self._runner = runner
            logger.info('DLNA media server: url=%s file=%s size=%s', self.url, path, path.stat().st_size)
            return self.url
        except BaseException:
            await runner.cleanup()
            raise

    async def _start_hls(self, path, address, resolution, position, executable, encoder, speed):
        self._hls_directory = tempfile.TemporaryDirectory(prefix='cast-hls-')
        directory = Path(self._hls_directory.name)
        route = '/' + secrets.token_urlsafe(24)
        width, bitrate, level = CAST_VIDEO_PROFILES[resolution]
        filters = f'scale=w=min(iw\\,{width}):h=min(ih\\,{resolution}):force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1'
        video_speed, audio_speed = cast_speed_filters(speed)
        command = [
            executable, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-threads', '4', '-ss', str(max(0, position)), '-readrate', str(speed), '-i', str(path),
            '-map', '0:v:0', '-map', '0:a:0?', '-sn', '-dn', '-vf', filters + video_speed, '-r', '30',
            *video_encoder_args(encoder, True), '-level:v', level, '-pix_fmt', 'yuv420p',
            '-b:v', bitrate, '-maxrate', bitrate, '-bufsize', '8000k', '-g', '60',
            *audio_speed, '-c:a', 'aac', '-b:a', '128k', '-ac', '2', '-ar', '48000', '-threads', '4',
            '-f', 'hls', '-hls_time', '2', '-hls_list_size', '6', '-hls_delete_threshold', '3',
            '-hls_flags', 'delete_segments+independent_segments+temp_file',
            '-hls_segment_filename', str(directory / 'segment%06d.ts'), str(directory / 'video.m3u8'),
        ]

        def record_bytes(size):
            self._record_bytes(size)
            self.stream_started = True

        async def serve(request):
            name = request.match_info['name']
            segment = (len(name) == 16 and name.startswith('segment') and name.endswith('.ts')
                       and all('0' <= digit <= '9' for digit in name[7:13]))
            if name != 'video.m3u8' and not segment:
                raise web.HTTPNotFound()
            file = directory / name
            if not file.is_file():
                raise web.HTTPNotFound()
            self.request_count += 1
            if name == 'video.m3u8':
                return web.Response(body=file.read_bytes(), content_type='application/vnd.apple.mpegurl',
                                    headers={'Cache-Control': 'no-store'})
            return MeteredFileResponse(file, record_bytes, headers={'Content-Type': 'video/mp2t', 'Cache-Control': 'no-store'})

        async def watch(process):
            _, detail = await process.communicate()
            self._processes.discard(process)
            if process.returncode and self._runner is not None:
                self.error = '实时 HLS 转码失败：' + (detail.decode('utf-8', errors='replace')[-1500:] or f'FFmpeg exit {process.returncode}')

        app = web.Application()
        app.router.add_get(route + '/{name}', serve)
        self._runner = web.AppRunner(app, access_log=logging.getLogger('casting.http'), shutdown_timeout=1)
        try:
            await self._runner.setup()
            await web.TCPSite(self._runner, address, 0).start()
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            self._processes.add(process)
            self._hls_task = asyncio.create_task(watch(process))

            async def ready():
                while True:
                    if ((directory / 'video.m3u8').is_file()
                            and ((directory / 'segment000001.ts').is_file() or process.returncode == 0)):
                        return
                    if process.returncode is not None:
                        await self._hls_task
                        raise RuntimeError(self.error or 'FFmpeg did not output HLS video')
                    await asyncio.sleep(0.05)

            await asyncio.wait_for(ready(), 15)
            self.url = f'http://{address}:{self._runner.addresses[0][1]}{route}/video.m3u8'
            return self.url
        except BaseException:
            await self.close()
            raise

    async def _serve_stream(self, request, path, resolution, position, executable, encoder, speed):
        headers = {
            'Content-Type': 'video/mpeg', 'Cache-Control': 'no-store',
            'Accept-Ranges': 'none', 'transferMode.dlna.org': 'Streaming',
            'contentFeatures.dlna.org': 'DLNA.ORG_OP=00;DLNA.ORG_CI=1',
        }
        if request.method == 'HEAD':
            return web.StreamResponse(headers=headers)
        if self._requests:
            raise web.HTTPConflict(text='A live stream is already active')
        task = asyncio.current_task()
        self._requests.add(task)
        process = None
        errors = None
        response = None
        width, bitrate, level = CAST_VIDEO_PROFILES[resolution]
        filters = f'scale=w=min(iw\\,{width}):h=min(ih\\,{resolution}):force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1'
        video_speed, audio_speed = cast_speed_filters(speed)
        filters += video_speed
        command = [
            executable, '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-threads', '4', '-ss', str(max(0, position)), '-readrate', str(speed), '-i', str(path),
            '-map', '0:v:0', '-map', '0:a:0?', '-sn', '-dn', '-vf', filters, '-r', '30',
            *video_encoder_args(encoder, True), '-level:v', level, '-pix_fmt', 'yuv420p',
            '-b:v', bitrate, '-maxrate', bitrate, '-bufsize', '4000k', '-g', '60',
            *audio_speed, '-c:a', 'aac', '-b:a', '128k', '-ac', '2', '-ar', '48000', '-threads', '4',
            '-f', 'mpegts', '-mpegts_flags', '+resend_headers', '-muxdelay', '0', '-muxpreload', '0', 'pipe:1',
        ]
        try:
            logger.info('DLNA live transcode begin: file=%s resolution=%s position=%s encoder=%s speed=%s', path, resolution, position, encoder, speed)
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            self._processes.add(process)
            errors = asyncio.create_task(process.stderr.read())
            first = await asyncio.wait_for(process.stdout.read(65536), 15)
            if not first:
                detail = (await errors).decode('utf-8', errors='replace')
                raise RuntimeError(detail[-1500:] or 'FFmpeg did not output video')
            response = web.StreamResponse(headers=headers)
            await response.prepare(request)
            await response.write(first)
            self._record_bytes(len(first))
            self.stream_started = True
            logger.info('DLNA live stream first bytes: bytes=%s', len(first))
            while chunk := await process.stdout.read(65536):
                await response.write(chunk)
                self._record_bytes(len(chunk))
            returncode = await process.wait()
            detail = (await errors).decode('utf-8', errors='replace')
            if returncode != 0:
                raise RuntimeError(detail[-1500:] or f'FFmpeg exit {returncode}')
            await response.write_eof()
            return response
        except (ConnectionError, asyncio.CancelledError):
            logger.info('DLNA live stream disconnected')
            raise
        except Exception as error:
            self.error = '实时转码失败：' + (str(error) or type(error).__name__)
            logger.exception('DLNA live transcode failed')
            if response is None:
                raise web.HTTPInternalServerError(text='Live transcoding failed') from error
            response.force_close()
            return response
        finally:
            if process is not None:
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                if errors is not None:
                    errors.cancel()
                    await asyncio.gather(errors, return_exceptions=True)
                await process.communicate()
                self._processes.discard(process)
            self._requests.discard(task)

    async def close(self):
        requests = list(self._requests)
        for task in requests:
            task.cancel()
        await asyncio.gather(*requests, return_exceptions=True)
        if self._runner is not None:
            logger.info('DLNA media server closing: requests=%s', self.request_count)
            await self._runner.cleanup()
            self._runner = None
        for process in list(self._processes):
            if process.returncode is None:
                process.kill()
            await process.wait()
        if self._hls_task is not None:
            await asyncio.gather(self._hls_task, return_exceptions=True)
            self._hls_task = None
        self._processes.clear()
        if self._hls_directory is not None:
            self._hls_directory.cleanup()
            self._hls_directory = None
        self.url = None
        self.bytes_sent = 0
        self._transfer_samples.clear()


@dataclass(frozen=True)
class CastDevice:
    name: str
    location: str
    host: str
    udn: str
    protocol: str = 'dlna'


def local_addresses() -> list[str]:
    addresses = set()
    for interface in QNetworkInterface.allInterfaces():
        if not interface.flags() & QNetworkInterface.InterfaceFlag.IsUp:
            continue
        for entry in interface.addressEntries():
            if entry.ip().protocol() != QAbstractSocket.NetworkLayerProtocol.IPv4Protocol:
                continue
            address = ipaddress.ip_address(entry.ip().toString())
            if not (address.is_loopback or address.is_link_local or address.is_unspecified):
                addresses.add(str(address))
    return sorted(addresses)


def route_address(host: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.connect((host, 80))
        return connection.getsockname()[0]


async def search_devices(callback, address):
    listener = SsdpSearchListener(
        async_callback=callback, timeout=4,
        search_target='ssdp:all',
        source=(address, 0),
    )
    try:
        await listener.async_start()
        for target in ('ssdp:all', 'upnp:rootdevice',
                       'urn:schemas-upnp-org:device:MediaRenderer:1'):
            listener.search_target = target
            listener.async_search()
        await asyncio.sleep(4)
    finally:
        listener.async_stop()


def normalize_renderer_response(action, response):
    if (action.name != 'GetCurrentTransportActions' or response.status_code != 200
            or not isinstance(response.body, str)):
        return response
    try:
        root = ElementTree.fromstring(response.body)
    except (ElementTree.ParseError, DefusedXmlException):
        return response
    body = root.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
    if body is None or len(body) != 1:
        return response
    result = body[0]
    service_type = action.service.service_type
    if (result.tag != f'{{{service_type}}}SetRecordQualityMode'
            or len(result) != 1 or result[0].tag != 'Actions'):
        return response
    result.tag = f'{{{service_type}}}GetCurrentTransportActionsResponse'
    return HttpResponse(response.status_code, response.headers,
                        ElementTree.tostring(root, encoding='unicode'))


class CastManager(QObject):
    devicesFound = pyqtSignal(object)
    sessionChanged = pyqtSignal(object)
    started = pyqtSignal(object)
    stopped = pyqtSignal(object)
    failed = pyqtSignal(str)
    busyChanged = pyqtSignal(bool)
    stageChanged = pyqtSignal(str)
    encodersFound = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.device = None
        self.file_path = None
        self.busy = False
        self.stage = '空闲'
        self._playback_started = False
        self._rebuilding = False
        self._start_deadline = None
        self._start_position = 0
        self._live_resolution = None
        self._stream_offset = 0
        self._media_duration = 0
        self._live_encoder = 'cpu'
        self._playback_speed = 1
        self._encoder_task = None
        self._notify_server = None
        self._event_profile = None
        self._events_enabled = False
        self._monitor_task = None
        self._state_wakeup = None
        self._position_anchor = 0
        self._position_clock = None
        self._position_playing = False
        self._future = None
        self._closed = False
        self._renderer = None
        self._profiles = {}
        self._server = MediaServer()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='DLNA')
        self._thread.start()

    @property
    def connected(self):
        return self.device is not None

    @property
    def log_path(self):
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                return handler.baseFilename
        return None

    def set_debug(self, enabled):
        level = logging.DEBUG if enabled else logging.WARNING
        for name in ('casting', 'async_upnp_client', 'aiohttp', 'pyatv', 'zeroconf'):
            logging.getLogger(name).setLevel(level)
        logger.info('DLNA debug logging: enabled=%s log=%s', enabled, self.log_path)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        self._loop.run_until_complete(self._loop.shutdown_asyncgens())
        self._loop.run_until_complete(self._loop.shutdown_default_executor())
        self._loop.close()

    def _submit(self, operation, timeout=40):
        if self.busy or self._closed:
            return False
        self.busy = True
        self.busyChanged.emit(True)
        self._future = asyncio.run_coroutine_threadsafe(self._execute(operation, timeout), self._loop)
        return True

    def cancel(self):
        if self.busy and not self.connected and self._future is not None:
            return self._future.cancel()
        return False

    async def _execute(self, operation, timeout=40):
        try:
            await asyncio.wait_for(operation(), timeout=timeout)
        except asyncio.CancelledError:
            logger.info('DLNA operation cancelled: stage=%s', self.stage)
            if not self._closed:
                self.failed.emit('已取消投屏')
        except Exception as error:
            logger.exception('DLNA operation failed: stage=%s', self.stage)
            if not self._closed:
                self.failed.emit(str(error) or f'{self.stage}超时或失败（{type(error).__name__}）')
        finally:
            self._future = None
            self.busy = False
            if not self._closed:
                self.busyChanged.emit(False)

    async def _step(self, name, operation):
        self.stage = name
        self.stageChanged.emit(name)
        started_at = time.monotonic()
        logger.info('DLNA stage begin: %s', name)
        try:
            result = await operation()
        except Exception as error:
            logger.exception('DLNA stage failed: %s elapsed=%.2fs', name, time.monotonic() - started_at)
            timeout = (isinstance(error, TimeoutError) or isinstance(error.__cause__, TimeoutError)
                       or 'Timeout' in type(error).__name__)
            detail = '设备响应超时' if timeout else (str(error) or type(error).__name__)
            raise RuntimeError(f'{name}失败：{detail}') from error
        logger.info('DLNA stage complete: %s elapsed=%.2fs', name, time.monotonic() - started_at)
        return result

    def scan_encoders(self):
        if not self._closed:
            return asyncio.run_coroutine_threadsafe(self._available_encoders(), self._loop)
        return None

    async def _probe_encoders(self):
        available = ['cpu']
        for encoder in ('nvenc', 'amf', 'qsv'):
            try:
                if await probe_video_encoder(encoder):
                    available.append(encoder)
            except Exception:
                logger.exception('DLNA GPU probe failed: encoder=%s', encoder)
        return available

    async def _available_encoders(self):
        if self._encoder_task is None:
            self._encoder_task = asyncio.create_task(self._probe_encoders())
        available = await asyncio.shield(self._encoder_task)
        if not self._closed:
            self.encodersFound.emit(available)
        return available

    async def _select_encoder(self, requested):
        if requested == 'cpu':
            return 'cpu'
        if requested not in ('auto', 'nvenc', 'amf', 'qsv'):
            raise ValueError('Unsupported video encoder')
        available = await self._available_encoders()
        if requested == 'auto':
            return next((encoder for encoder in ('nvenc', 'amf', 'qsv') if encoder in available), 'cpu')
        if requested not in available:
            raise RuntimeError('所选 GPU 编码器不可用，请选择自动或 CPU')
        return requested

    def search(self):
        return self._submit(lambda: self._discover(local_addresses()))

    def add_device(self, location):
        return self._submit(lambda: self._discover([], location.strip()))

    async def _discover(self, addresses, manual_location=None):
        self.stage = '搜索设备'
        logger.info('DLNA discovery: interfaces=%s', addresses)
        if not addresses and manual_location is None:
            raise RuntimeError("没有可用的局域网连接")
        locations = {location for location, profile in self._profiles.items() if not isinstance(profile, AirPlayReceiver)}
        airplay_locations = {location: profile.name for location, profile in self._profiles.items() if isinstance(profile, AirPlayReceiver)}
        airplay_manual = None
        if manual_location is not None and (manual_location.startswith('airplay://') or '://' not in manual_location
                                            or urlsplit(manual_location).path == '/server-info'):
            parsed = urlsplit(manual_location if '://' in manual_location else 'airplay://' + manual_location)
            if parsed.scheme not in ('http', 'airplay'):
                raise ValueError('AirPlay 仅支持局域网 HTTP 地址或 airplay:// 地址')
            if parsed.username is not None or parsed.password is not None:
                raise ValueError('AirPlay 地址不能包含用户名或密码')
            airplay_manual = f'http://{parsed.hostname}:{parsed.port or 7000}/server-info'
            await inspect_airplay(airplay_manual)
            airplay_locations[airplay_manual] = f'AirPlay {parsed.hostname}'

        async def found(headers):
            location = headers.get('location', '')
            try:
                parsed = urlsplit(location)
                host = ipaddress.ip_address(parsed.hostname or '')
            except ValueError:
                return
            if (parsed.scheme == 'http' and host.version == 4 and host.is_private
                    and parsed.username is None and parsed.password is None
                    and not (host.is_loopback or host.is_unspecified or host.is_multicast)):
                locations.add(location)

        if manual_location is not None and airplay_manual is None:
            await found({'location': manual_location})
            if manual_location not in locations:
                raise ValueError("请输入局域网 IPv4 设备的 HTTP 描述地址")
            logger.info('DLNA manual discovery: location=%s', manual_location)
        elif manual_location is None:
            results = await asyncio.gather(*[
                search_devices(found, address=address)
                for address in addresses
            ], return_exceptions=True)
            ssdp_failed = all(isinstance(result, Exception) for result in results) and not locations
            try:
                for name, location in await discover_airplay():
                    airplay_locations[location] = name
            except Exception:
                logger.warning('AirPlay discovery failed; DLNA discovery retained', exc_info=True)
            if ssdp_failed and not airplay_locations:
                raise RuntimeError("设备搜索失败，请检查网络与防火墙")
        factory = UpnpFactory(AiohttpRequester(timeout=5), non_strict=True,
                              on_post_call_action=normalize_renderer_response)
        limit = asyncio.Semaphore(6)
        errors = []

        async def describe(location):
            async with limit:
                try:
                    root = await asyncio.wait_for(factory.async_create_device(location), 10)
                    for candidate in root.all_devices:
                        if candidate.device_type not in DmrDevice.DEVICE_TYPES:
                            continue
                        profile = DmrDevice(candidate, None)
                        if not (profile.has_play_media and profile.has_play):
                            continue
                        device = CastDevice(candidate.friendly_name, location,
                                            urlsplit(location).hostname, candidate.udn)
                        self._profiles[location] = profile
                        logger.info('DLNA receiver discovered: name=%s location=%s', device.name, location)
                        return device
                except Exception as error:
                    errors.append(location + ": " + (str(error) or type(error).__name__))
                    return None
            return None

        devices = await asyncio.gather(*[describe(location) for location in sorted(locations)[:18]])
        unique = {device.udn: device for device in devices if device is not None}
        dlna_hosts = {device.host for device in unique.values()}
        for location, name in sorted(airplay_locations.items()):
            try:
                await inspect_airplay(location)
                parsed = urlsplit(location)
                if parsed.hostname in dlna_hosts and location != airplay_manual:
                    continue
                profile = AirPlayReceiver(parsed.hostname, parsed.port or 7000, name)
                device = CastDevice(name, location, parsed.hostname, 'airplay:' + parsed.hostname, 'airplay')
                self._profiles[location] = profile
                unique[device.udn] = device
                logger.info('AirPlay video receiver discovered: name=%s location=%s', name, location)
            except Exception:
                logger.debug('AirPlay receiver unavailable: %s', location, exc_info=True)
        if not unique and errors:
            raise RuntimeError("收到设备响应，但读取设备信息失败：\n" + "\n".join(errors[:3]))
        if manual_location is not None and not any(device.location == (airplay_manual or manual_location) for device in unique.values()):
            raise RuntimeError("该地址不是可用的 DLNA 播放接收器")
        self.devicesFound.emit(sorted(unique.values(), key=lambda device: device.name.casefold()))

    def start(self, device: CastDevice, file_path: str, position: float = 0, resolution=None, delivery='stream', duration=0, encoder='cpu', speed=1):
        return self._submit(lambda: self._start(device, file_path, position, resolution, delivery, duration, encoder, speed), timeout=None)

    async def _start(self, device, file_path, position, resolution=None, delivery='stream', duration=0, encoder='cpu', speed=1):
        cast_speed_filters(speed)
        if resolution is None and speed != 1:
            raise RuntimeError('原画直传不支持倍速，请选择兼容画质')
        if self.connected:
            raise RuntimeError("请先停止当前投屏")
        profile = self._profiles.get(device.location)
        if profile is None:
            raise RuntimeError("设备已失效，请重新搜索")
        if delivery not in ('stream', 'file'):
            raise ValueError('Unsupported casting delivery mode')
        live = resolution is not None and delivery == 'stream'
        logger.info('DLNA start: receiver=%s host=%s description=%s file=%s position=%s',
                    device.name, device.host, device.location, file_path, position)
        session_assigned = False
        transport_assigned = False
        try:
            selected_encoder = await self._select_encoder(encoder) if resolution is not None else 'cpu'
            logger.info('DLNA selected video encoder: requested=%s selected=%s', encoder, selected_encoder)
            media_path = file_path
            if resolution is not None and not live:
                media_path = await self._step(
                    f'准备 {resolution}p 兼容视频',
                    lambda: prepare_cast_media(file_path, resolution, self.stageChanged.emit, encoder=selected_encoder, speed=speed)
                )
            if live:
                url = await self._step('启动实时视频服务', lambda: self._server.start(
                    file_path, route_address(device.host), resolution=resolution, position=position, encoder=selected_encoder, speed=speed,
                    **({'hls': True} if isinstance(profile, AirPlayReceiver) else {})
                ))
            else:
                url = await self._step('启动视频服务', lambda: self._server.start(media_path, route_address(device.host)))
            mime_type = 'video/mpeg' if live else ('video/mp4' if resolution is not None else (mimetypes.guess_type(file_path)[0] or 'video/mp4'))
            metadata = await profile.construct_play_media_metadata(
                url, Path(file_path).name, override_mime_type=mime_type,
                override_upnp_class='object.item.videoItem',
                override_dlna_features='DLNA.ORG_OP=00;DLNA.ORG_CI=1' if live else '*'
            )
            transport_assigned = True
            await self._play_transport(profile, url, Path(file_path).name, metadata)
            self.device = device
            self.file_path = file_path
            self._renderer = profile
            self._live_resolution = resolution if live else None
            self._live_encoder = selected_encoder
            self._playback_speed = speed
            self._stream_offset = max(0, position) if live else 0
            self._media_duration = max(0, duration or 0)
            session_assigned = True
            self._playback_started = False
            self._start_deadline = time.monotonic() + (30 if live else 15)
            self._start_position = 0 if live else position
            await self._start_monitor(profile, device.host)
            await self._update()
            if self._renderer is not None and self._state_wakeup is not None:
                self._monitor_task = asyncio.create_task(self._monitor_session())
        except BaseException:
            logger.warning('DLNA start did not complete: stage=%s media_requests=%s',
                           self.stage, self._server.request_count)
            if self.connected:
                await self._disconnect(stop_remote=False)
            elif not session_assigned:
                if transport_assigned:
                    try:
                        await asyncio.wait_for(profile.async_stop(), 2)
                    except Exception:
                        pass
                try:
                    await self._server.close()
                finally:
                    if isinstance(profile, AirPlayReceiver):
                        await profile.close()
            raise

    async def _play_transport(self, profile, url, title, metadata):
        await self._step('设置 AirPlay 视频地址' if isinstance(profile, AirPlayReceiver) else '发送视频地址（SetAVTransportURI）',
                         lambda: profile.async_set_transport_uri(url, title, metadata))
        await self._step('等待设备就绪', profile.async_wait_for_can_play)
        await self._step('开始播放（AirPlay）' if isinstance(profile, AirPlayReceiver) else '开始播放（Play）', profile.async_play)

    async def _start_monitor(self, profile, host):
        self._state_wakeup = asyncio.Event()
        if isinstance(profile, AirPlayReceiver):
            self._reset_position_clock(from_receiver=True)
            return
        try:
            server = AiohttpNotifyServer(AiohttpRequester(timeout=1), source=(route_address(host), 0))
            self._notify_server = server
            await server.async_start_server()
            event_profile = DmrDevice(profile.profile_device, server.event_handler)
            self._event_profile = event_profile
            event_profile.on_event = lambda service, variables: self._on_renderer_event(event_profile, service, variables)
            await asyncio.wait_for(event_profile.async_subscribe_services(auto_resubscribe=True), 5)
            if not event_profile.is_subscribed:
                raise RuntimeError('Receiver has no event subscriptions')
            self._renderer = event_profile
            self._events_enabled = True
            logger.info('DLNA event subscription active: callback=%s', server.callback_url)
        except Exception:
            logger.warning('DLNA event subscription unavailable; automatic polling disabled', exc_info=True)
            await self._close_events()
            self._state_wakeup = asyncio.Event()
        self._reset_position_clock(from_receiver=True)

    def _reset_position_clock(self, from_receiver=False, position=None):
        if self._renderer is None:
            return
        if position is None:
            position = ((self._renderer.media_position or 0) * self._playback_speed + self._stream_offset
                        if from_receiver else self.snapshot(estimate=True)['position'])
        self._position_anchor = position
        self._position_clock = time.monotonic()
        state = self._renderer.transport_state
        self._position_playing = self._playback_started and bool(state and state.value == 'PLAYING')

    def _on_renderer_event(self, profile, service, variables):
        if self._closed or profile is not self._event_profile:
            return
        if not variables:
            self._events_enabled = False
            logger.warning('DLNA event subscription lost; automatic polling disabled')
        names = {variable.name for variable in variables}
        if profile is self._renderer:
            if 'RelativeTimePosition' in names:
                self._reset_position_clock(from_receiver=True)
            elif 'TransportState' in names:
                self._reset_position_clock()
        if self._state_wakeup is not None:
            self._state_wakeup.set()
        logger.debug('DLNA event: service=%s variables=%s', service.service_id, [variable.name for variable in variables])

    async def _monitor_session(self):
        delay = 0.5
        next_query = time.monotonic() + delay
        try:
            while self._renderer is not None and not self._closed:
                try:
                    await asyncio.wait_for(self._state_wakeup.wait(), 0.25)
                except TimeoutError:
                    pass
                self._state_wakeup.clear()
                if self.busy or self._rebuilding:
                    continue
                if self._live_resolution is not None and self._server.error:
                    raise RuntimeError(self._server.error)
                if not self._playback_started and time.monotonic() >= next_query:
                    await self._update()
                    delay = min(delay * 2, 5)
                    next_query = time.monotonic() + delay
                else:
                    await self._publish_state(log_state=False)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception('DLNA event monitor failed')
            if self._renderer is not None:
                await self._disconnect(stop_remote=False)
            if not self._closed:
                self.failed.emit(str(error) or type(error).__name__)

    async def _close_events(self):
        task, self._monitor_task = self._monitor_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        profile, self._event_profile = self._event_profile, None
        self._events_enabled = False
        self._state_wakeup = None
        if profile is not None:
            profile.on_event = None
            try:
                await profile.async_unsubscribe_services()
            except Exception:
                logger.debug('DLNA unsubscribe failed', exc_info=True)
        if self._notify_server is not None:
            server, self._notify_server = self._notify_server, None
            await server.async_stop_server()

    def update(self):
        if self.connected:
            return self._submit(self._update)
        return False

    async def _update(self):
        if self._renderer is None:
            return
        try:
            if self._live_resolution is not None and self._server.error:
                raise RuntimeError(self._server.error)
            operation = self._renderer.async_update
            if self._start_deadline is not None:
                remaining = max(0.01, self._start_deadline - time.monotonic())
                operation = lambda: asyncio.wait_for(self._renderer.async_update(), remaining)
            await self._step('读取设备播放状态', operation)
            if self._position_clock is not None:
                self._reset_position_clock(from_receiver=True)
        except BaseException:
            await self._disconnect(stop_remote=False)
            raise
        await self._publish_state()

    async def _publish_state(self, log_state=True):
        if self._renderer is None or self._rebuilding:
            return
        state = self.snapshot(estimate=True)
        if log_state:
            logger.info('DLNA playback state: state=%s confirmed=%s media_requests=%s',
                        state['state'], self._playback_started, self._server.request_count)
        media_ready = self._live_resolution is None or self._server.stream_started
        if isinstance(self._renderer, AirPlayReceiver):
            media_ready = self._server.bytes_sent > 0
        if state['state'] in ('PLAYING', 'PAUSED_PLAYBACK') and media_ready:
            if not self._playback_started:
                self._playback_started = True
                self._start_deadline = None
                if self._position_clock is not None:
                    self._reset_position_clock(from_receiver=True)
                self.started.emit({'file': self.file_path, 'device': self.device.name})
                if self._start_position > 0 and (self._renderer.has_seek_rel_time or self._renderer.has_seek_abs_time):
                    try:
                        await self._step('恢复进度（Seek）', lambda: self._seek(self._start_position))
                        await self._step('刷新跳转后的播放进度', self._renderer.async_update)
                        if self._position_clock is not None:
                            self._reset_position_clock(from_receiver=True)
                        state = self.snapshot()
                    except Exception as error:
                        self.failed.emit("投屏已开始，但未能恢复进度：" + str(error))
        elif not self._playback_started and self._start_deadline is not None:
            if time.monotonic() >= self._start_deadline:
                requests = self._server.request_count
                await self._disconnect(stop_remote=state['state'] not in ('STOPPED', 'NO_MEDIA_PRESENT'))
                raise RuntimeError(f"设备未进入播放状态（{state['state']}，视频请求数 {requests}），已结束投屏，可再次尝试；请检查设备是否提示格式不支持")
            state['state'] = 'TRANSITIONING'
        elif state['state'] in ('STOPPED', 'NO_MEDIA_PRESENT'):
            await self._disconnect(stop_remote=False)
            return
        self.sessionChanged.emit(state)

    def snapshot(self, estimate=False):
        profile = self._renderer
        if profile is None:
            return {}
        state = profile.transport_state
        position = (profile.media_position or 0) * self._playback_speed + self._stream_offset
        duration = self._media_duration or (profile.media_duration or 0) * self._playback_speed
        if estimate and self._position_clock is not None:
            elapsed = max(0, time.monotonic() - self._position_clock) if self._position_playing else 0
            position = self._position_anchor + elapsed * self._playback_speed
            if duration:
                position = min(position, duration)
        return {
            'device': self.device.name,
            'file': self.file_path,
            'state': state.value if state else 'UNKNOWN',
            'position': position,
            'duration': duration,
            'position_estimated': estimate and self._position_clock is not None,
            'status_sync': 'events' if self._events_enabled else 'manual',
            'transfer_mbps': self._server.transfer_mbps,
            'bytes_sent': self._server.bytes_sent,
            'speed': self._playback_speed,
            'can_speed': self._live_resolution is not None,
            'volume': profile.volume_level,
            'can_pause': profile.has_pause,
            'can_seek': self._live_resolution is not None or profile.has_seek_rel_time or profile.has_seek_abs_time,
            'can_volume': profile.has_volume_level,
        }

    def command(self, action: str, value=None):
        return self._submit(lambda: self._command(action, value))

    async def _seek(self, seconds):
        if self._live_resolution is not None:
            position = max(0, int(seconds))
            if self._media_duration:
                position = min(position, self._media_duration)
            self._rebuilding = True
            try:
                await self._step('停止旧实时流', self._renderer.async_stop)
                url = await self._step('重建实时视频流', lambda: self._server.start(
                    self.file_path, route_address(self.device.host), resolution=self._live_resolution,
                    position=position, encoder=self._live_encoder, speed=self._playback_speed,
                    **({'hls': True} if isinstance(self._renderer, AirPlayReceiver) else {})
                ))
                metadata = await self._renderer.construct_play_media_metadata(
                    url, Path(self.file_path).name, override_mime_type='video/mpeg',
                    override_upnp_class='object.item.videoItem', override_dlna_features='DLNA.ORG_OP=00;DLNA.ORG_CI=1'
                )
                await self._play_transport(self._renderer, url, Path(self.file_path).name, metadata)
                self._stream_offset = position
                self._playback_started = False
                self._start_deadline = time.monotonic() + 30
                if self._position_clock is not None:
                    self._reset_position_clock(position=position)
            except BaseException:
                await self._disconnect(stop_remote=False)
                raise
            finally:
                self._rebuilding = False
            return
        target = timedelta(seconds=max(0, int(seconds / self._playback_speed)))
        if self._renderer.has_seek_rel_time:
            await self._renderer.async_seek_rel_time(target)
        elif self._renderer.has_seek_abs_time:
            await self._renderer.async_seek_abs_time(target)
        else:
            raise RuntimeError("设备不支持调整进度")

    async def _command(self, action, value):
        if self._renderer is None:
            raise RuntimeError("尚未连接投屏设备")
        if action == 'play':
            if (isinstance(self._renderer, AirPlayReceiver) and self._live_resolution is not None
                    and self._renderer.transport_state == TransportState.PAUSED_PLAYBACK):
                await self._seek(self.snapshot(estimate=True)['position'])
            else:
                await self._renderer.async_play()
        elif action == 'pause':
            await self._renderer.async_pause()
        elif action == 'seek':
            await self._seek(value)
        elif action == 'speed':
            cast_speed_filters(value)
            if self._live_resolution is None:
                raise RuntimeError('仅实时兼容投屏支持播放中切换倍速；完整缓存需停止后重新选择')
            if value != self._playback_speed:
                state = self.snapshot(estimate=True)
                self._playback_speed = value
                await self._seek(state['position'])
                if state['state'] == 'PAUSED_PLAYBACK':
                    await self._renderer.async_pause()
        elif action == 'volume':
            await self._renderer.async_set_volume_level(max(0, min(1, value)))
        elif action == 'stop':
            await self._disconnect()
            return
        else:
            raise ValueError("Unknown cast command")
        await self._update()

    async def _disconnect(self, stop_remote=True):
        previous = self.snapshot(estimate=True)
        profile = self._renderer
        try:
            if stop_remote and self._renderer is not None:
                await asyncio.wait_for(self._renderer.async_stop(), 2)
        finally:
            self._renderer = None
            self.device = None
            self.file_path = None
            self._playback_started = False
            self._start_deadline = None
            self._start_position = 0
            self._live_resolution = None
            self._stream_offset = 0
            self._media_duration = 0
            self._live_encoder = 'cpu'
            self._playback_speed = 1
            self._position_clock = None
            self._position_playing = False
            try:
                await self._close_events()
            finally:
                try:
                    if isinstance(profile, AirPlayReceiver):
                        await profile.close()
                finally:
                    await self._server.close()
            if not self._closed:
                self.stopped.emit(previous)

    async def _shutdown(self):
        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task is not current]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        try:
            await asyncio.wait_for(self._disconnect(), 8)
        except Exception:
            await self._server.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        try:
            future.result(timeout=10)
        except Exception:
            pass
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2)