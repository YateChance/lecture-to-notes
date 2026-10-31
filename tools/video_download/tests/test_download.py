"""Real local HTTP/media fixtures: no external accounts, sites or course downloads."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DownloadError
from download import make_plan, perform


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe') and shutil.which('curl'), '需要FFmpeg与curl')
class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.root = Path(cls.workspace.name)
        cls.media = cls.root / 'fixture.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
            'color=c=blue:s=160x90:r=10', '-t', '1', '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(cls.media)], check=True)
        data = cls.media.read_bytes()
        cls.http_state = {'drop': False, 'ranges': [], 'etag': '"fixture-1"'}
        state = cls.http_state

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path.startswith('/login'):
                    body = b'<html>Please sign in</html>'
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                requested = self.headers.get('Range')
                start = 0
                if requested:
                    state['ranges'].append((requested, self.headers.get('If-Range')))
                    if self.headers.get('If-Range') == state['etag']:
                        start = int(requested.removeprefix('bytes=').split('-')[0])
                        self.send_response(206)
                        self.send_header('Content-Range', f'bytes {start}-{len(data)-1}/{len(data)}')
                    else:
                        self.send_response(200)
                else:
                    self.send_response(200)
                body = data[start:]
                self.send_header('Content-Type', 'video/mp4')
                self.send_header('ETag', state['etag'])
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if state['drop'] and not requested:
                    state['drop'] = False
                    self.wfile.write(body[:len(body)//2])
                    self.wfile.flush()
                    self.close_connection = True
                else:
                    self.wfile.write(body)

        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.workspace.cleanup()

    def setUp(self):
        self.project = self.root / self._testMethodName
        self.project.mkdir()
        self.http_state.update(drop=False, ranges=[], etag='"fixture-1"')

    def request(self, path='/video.mp4?token=do-not-persist'):
        return {'schema_version': '1.0', 'lesson': '测试/第01周（1）-样例',
                'filename': 'lecture.mp4', 'adapter': 'direct_http',
                'media_url': self.url + path, 'expected': {'duration_seconds': 1, 'duration_tolerance_seconds': .2}}

    def target(self):
        return self.project / 'outputs/测试/第01周（1）-样例/00_sources/video/lecture.mp4'

    def test_verified_download_and_no_overwrite(self):
        receipt = perform(self.request(), self.project)
        self.assertEqual(self.target().read_bytes(), self.media.read_bytes())
        self.assertEqual(receipt['sha256'], hashlib.sha256(self.media.read_bytes()).hexdigest())
        metadata = '\n'.join(p.read_text() for p in self.project.rglob('*.json*'))
        self.assertNotIn('do-not-persist', metadata)
        with self.assertRaises(DownloadError):
            perform(self.request(), self.project)
        self.assertEqual(self.target().read_bytes(), self.media.read_bytes())

    def test_login_html_is_not_completed_video(self):
        with self.assertRaises(DownloadError):
            perform(self.request('/login'), self.project)
        self.assertFalse(self.target().exists())
        self.assertFalse(list(self.project.rglob('sources.jsonl')))

    def test_interrupted_download_resumes_with_etag(self):
        self.http_state['drop'] = True
        with self.assertRaises(DownloadError):
            perform(self.request(), self.project)
        self.assertTrue(self.target().with_name('lecture.mp4.part').exists())
        receipt = perform(self.request(), self.project)
        self.assertTrue(receipt['transport']['resumed'])
        self.assertTrue(self.http_state['ranges'])
        self.assertEqual(self.target().read_bytes(), self.media.read_bytes())

    def test_changed_resource_refuses_resume_then_explicit_restart(self):
        self.http_state['drop'] = True
        with self.assertRaises(DownloadError):
            perform(self.request(), self.project)
        self.http_state['etag'] = '"fixture-2"'
        with self.assertRaises(DownloadError):
            perform(self.request(), self.project)
        self.assertFalse(self.target().exists())
        previous_requests = len(self.http_state['ranges'])
        with self.assertRaises(DownloadError):
            perform(self.request(), self.project)
        self.assertEqual(len(self.http_state['ranges']), previous_requests)
        perform(self.request(), self.project, restart=True)
        self.assertEqual(self.target().read_bytes(), self.media.read_bytes())
        self.assertTrue(list(self.project.rglob('attempts/*/*.part')))

    def test_local_import_validates_duration_and_keeps_original(self):
        request = self.request()
        request.update(adapter='local_file', local_file=str(self.media))
        request['expected'] = {'duration_seconds': 100}
        with self.assertRaises(DownloadError):
            perform(request, self.project)
        self.assertFalse(self.target().exists())
        request['expected'] = {'duration_seconds': 1}
        perform(request, self.project, restart=True)
        self.assertTrue(self.media.is_file())
        self.assertEqual(self.target().read_bytes(), self.media.read_bytes())

    def test_plan_browser_stream_and_private_request(self):
        plan = make_plan('https://classroom.msa.buaa.edu.cn/livingroom?course_id=example', '测试/第01周（1）-页面', self.project)
        self.assertEqual(plan['route'], 'requires_browser_discovery')
        self.assertEqual(plan['profile'], 'buaa_classroom')
        self.assertEqual(Path(plan['request_file']).stat().st_mode & 0o777, 0o600)
        stream = make_plan(self.url + '/stream.m3u8', '测试/第01周（1）-流', self.project)
        self.assertEqual(stream['route'], 'requires_stream_adapter')
        with self.assertRaises(DownloadError):
            perform(json.loads(Path(stream['request_file']).read_text()), self.project)
        bad = self.request()
        bad['lesson'] = '../outside'
        with self.assertRaises(DownloadError):
            perform(bad, self.project)


if __name__ == '__main__':
    unittest.main()
