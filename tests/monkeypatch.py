import io

def patch_urllib_networking():
    """
    patch RDFlib's use of urllib3 to use the requests_cache.

    We need to simulate a urllib3 response, which they also use as a file-like
    object, so we replace the old urllib3.response type with a bytestring of
    the response and manually set some attributes to match the ones used by rdflib.

    This is only intended to patch rdflib's network requests during testing, and is
    not in any way an actual monkeypatch for urllib.
    """
    import urllib.request
    from urllib.response import addinfourl
    import rdflib._networking

    def _patched_request(req, *args, **kwargs):
        #import requests
        res = requests.get(req.get_full_url())

        class UrllibString(io.BytesIO):
            def readable(self):
                return True
            def writable(self):
                return True
            def geturl(self):
                return res.url
            def info(self):
                return res.headers
            def close(self):
                pass

            class fp:
                mode = 'r'

        infourl = addinfourl(io.BytesIO(res.text.encode('utf-8')), res.headers, res.url)
        infourl.fp.mode = 'rb'
        # str_res = UrllibString(res.text.encode('utf-8'))
        # str_res.headers = res.headers
        # str_res.url = res.url
        return infourl

    urllib.request.urlopen = _patched_request
    rdflib._networking.urlopen = _patched_request

def run_patches():
    patch_urllib_networking()