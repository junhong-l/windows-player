import asyncio
import ipaddress
import math
import plistlib
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout
import pyatv
from async_upnp_client.profiles.dlna import TransportState
from pyatv.const import Protocol
from pyatv.protocols.raop import StreamContext
from pyatv.protocols.raop.protocols.airplayv1 import AirPlayV1
from pyatv.support.http import HttpConnection
from pyatv.support.rtsp import RtspSession


async def inspect_airplay(location):
    parsed = urlsplit(location)
    host = ipaddress.ip_address(parsed.hostname or '')
    if (parsed.scheme != 'http' or host.version != 4 or not host.is_private
            or host.is_loopback or host.is_unspecified or host.is_multicast
            or parsed.username is not None or parsed.password is not None):
        raise ValueError('AirPlay requires a private IPv4 HTTP address')
    port = parsed.port or 7000
    async with ClientSession(timeout=ClientTimeout(total=3)) as client:
        async with client.get(f'http://{host}:{port}/server-info', allow_redirects=False) as response:
            response.raise_for_status()
            body = await response.content.read(65537)
            if len(body) > 65536:
                raise ValueError('AirPlay server information is too large')
            info = plistlib.loads(body)
    if not isinstance(info, dict) or not int(info.get('features', 0)) & 1:
        raise ValueError('Receiver does not advertise AirPlay video')
    if not str(info.get('protovers', '1.0')).startswith('1.'):
        raise ValueError('Only legacy AirPlay video is supported')
    return info


async def discover_airplay():
    devices = await pyatv.scan(asyncio.get_running_loop(), timeout=3, protocol=Protocol.AirPlay)
    return [(device.name, f'http://{device.address}:{device.get_service(Protocol.AirPlay).port}/server-info')
            for device in devices if device.get_service(Protocol.AirPlay) is not None]


class AirPlayConnection(HttpConnection):
    def __init__(self, host, port):
        super().__init__()
        self.authority = f'{host}:{port}'

    async def send_and_receive(self, method, uri, **kwargs):
        headers = dict(kwargs.get('headers') or {})
        headers.setdefault('Host', self.authority)
        kwargs['headers'] = headers
        return await super().send_and_receive(method, uri, **kwargs)


class AirPlayReceiver:
    has_play_media = True
    has_play = True
    has_pause = True
    has_seek_rel_time = True
    has_seek_abs_time = False
    has_volume_level = False
    volume_level = None

    def __init__(self, host, port, name=None):
        self.host = host
        self.port = port
        self.name = name or f'AirPlay {host}'
        self.transport_state = TransportState.STOPPED
        self.media_position = 0
        self.media_duration = 0
        self._connection = None
        self._url = None
        self._sent = False
        self._play_requested = False

    async def _connect(self):
        if self._connection is None:
            _, self._connection = await asyncio.wait_for(
                asyncio.get_running_loop().create_connection(lambda: AirPlayConnection(self.host, self.port), self.host, self.port), 3
            )
        return self._connection

    async def construct_play_media_metadata(self, url, title, **kwargs):
        return None

    async def async_set_transport_uri(self, url, title, metadata=None):
        self._url = url
        self._sent = False
        self._play_requested = False
        self.media_position = 0
        self.media_duration = 0
        self.transport_state = TransportState.TRANSITIONING

    async def async_wait_for_can_play(self):
        return None

    async def async_play(self):
        connection = await self._connect()
        if not self._sent:
            protocol = AirPlayV1(StreamContext(), RtspSession(connection))
            self._play_requested = True
            response = await protocol.play_url(0, self._url)
            if not 200 <= response.code < 300:
                raise RuntimeError(f'AirPlay playback rejected: HTTP {response.code}')
            self._sent = True
        else:
            await connection.post('/rate?value=1')
            self.transport_state = TransportState.PLAYING

    async def async_pause(self):
        connection = await self._connect()
        await connection.post('/rate?value=0')
        self.transport_state = TransportState.PAUSED_PLAYBACK

    async def async_seek_rel_time(self, target):
        seconds = max(0, target.total_seconds())
        connection = await self._connect()
        await connection.post(f'/scrub?position={seconds:g}')
        self.media_position = seconds

    async def async_stop(self):
        if self._connection is not None and self._play_requested:
            await self._connection.post('/stop')
            self._play_requested = False
        self.transport_state = TransportState.STOPPED

    async def async_update(self):
        connection = await self._connect()
        response = await connection.get('/playback-info')
        body = response.body.encode('utf-8') if isinstance(response.body, str) else response.body
        info = plistlib.loads(body)
        if not isinstance(info, dict) or info.get('error'):
            raise RuntimeError('AirPlay returned invalid playback information')
        for key, attribute in (('position', 'media_position'), ('duration', 'media_duration')):
            if key in info:
                value = float(info[key])
                if not math.isfinite(value) or value < 0:
                    raise ValueError('Invalid AirPlay playback time')
                setattr(self, attribute, value)
        if info.get('readyToPlay') or info.get('duration', 0):
            if 'rate' in info:
                self.transport_state = TransportState.PAUSED_PLAYBACK if float(info['rate']) == 0 else TransportState.PLAYING
            elif self.transport_state != TransportState.PAUSED_PLAYBACK:
                self.transport_state = TransportState.PLAYING
        elif self.transport_state in (TransportState.PLAYING, TransportState.PAUSED_PLAYBACK):
            self.transport_state = TransportState.STOPPED

    async def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None