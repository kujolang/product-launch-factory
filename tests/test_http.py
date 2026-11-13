import http.client
import multiprocessing
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import launch
import core


def server(root,port):
    launch.RUNS=Path(root)
    launch.serve(port)

class FloorHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        core.write(root/'test-run/package/demo.mp4','0123456789')
        core.write(root/'test-run/input/private.txt','private')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.process=multiprocessing.Process(target=server,args=(root,self.port));self.process.start()
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',self.port),timeout=.05):break
            except OSError:time.sleep(.02)
    def tearDown(self):
        self.process.terminate();self.process.join();self.temp.cleanup()
    def request(self,path,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        conn.request('GET',path,headers=headers or {});response=conn.getresponse()
        result=response.status,dict(response.getheaders()),response.read();conn.close();return result
    def test_range_and_preview_policy(self):
        status,headers,body=self.request('/artifact/test-run/package/demo.mp4',{'Range':'bytes=2-5'})
        self.assertEqual(status,206);self.assertEqual(body,b'2345')
        self.assertEqual(headers['Content-Range'],'bytes 2-5/10')
        self.assertIn("script-src 'none'",headers['Content-Security-Policy'])
    def test_host_and_private_paths_rejected(self):
        self.assertEqual(self.request('/',{'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/artifact/test-run/input/private.txt')[0],404)
        self.assertEqual(self.request('/artifact/test-run/package/../input/private.txt')[0],404)
        self.assertEqual(self.request('/artifact/test-run/package/demo.mp4',{'Range':'bytes=20-'})[0],416)

if __name__=='__main__':unittest.main()
