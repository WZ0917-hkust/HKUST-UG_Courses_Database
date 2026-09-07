"""HTTP retries, pacing and semester discovery."""
import re
import time
from datetime import date
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .parser import subjects

BASE_URL = 'https://w5.ab.ust.hk/wcq/cgi-bin/'


def candidate_terms(today=None):
    today = today or date.today()
    year = today.year % 100
    if today.month >= 9:
        quarter = 0
    else:
        year -= 1
        quarter = 1 if today.month == 1 else 2 if today.month <= 5 else 3
    index = year * 4 + quarter
    return [f'{i // 4:02d}{(i % 4 + 1) * 10:02d}' for i in [index, index + 1, index - 1, index - 2, index - 3]]


class Client:
    def __init__(self, delay=0.5):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'HKUST-CourseDB/1.0'
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retry))

    def get(self, term, subject=None):
        time.sleep(self.delay)
        url = BASE_URL + term + ('/subject/' + subject if subject else '/')
        response = self.session.get(url, timeout=(10, 45))
        response.raise_for_status()
        if not re.search('/' + term + r'(?:/|$)', response.url):
            raise ValueError(f'{term}: redirected to another semester: {response.url}')
        response.encoding = 'utf-8'
        return response.text

    def discover(self, term):
        html = self.get(term)
        found = subjects(html)
        if not found:
            html = self.get(term, 'COMP')
            found = subjects(html)
        if not found:
            raise ValueError(f'{term}: no undergraduate subject links; semester may not be public')
        return found
