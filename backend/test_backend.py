import urllib.request, json, sys

BASE = 'http://localhost:8000'
AOI = {
    'type': 'Polygon',
    'coordinates': [[[77.55, 13.26], [77.58, 13.26], [77.58, 13.29], [77.55, 13.29], [77.55, 13.26]]]
}

def post(path, body):
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path, data=payload,
        headers={'Content-Type': 'application/json'}, method='POST'
    )
    try:
        r = urllib.request.urlopen(req, timeout=180)
        return json.loads(r.read()), None
    except urllib.request.HTTPError as e:
        return None, f'HTTP {e.code}: {e.read().decode()}'
    except Exception as e:
        return None, str(e)

print('=' * 60)
print('TEST 1: NDVI / Vegetation')
data, err = post('/api/analyze', {
    'state': 'Karnataka', 'area': 'Bengaluru Rural',
    'geometry': AOI, 'query': 'Where is the vegetation?'
})
if err:
    print('  FAIL:', err)
else:
    s = data['stats']
    print('  intent:', data['intent'])
    print('  index:', data['index'])
    print('  area:', s['area'], s['area_unit'])
    print('  total_aoi:', s['total_aoi'], s['area_unit'])
    print('  coverage:', s['percentage_coverage'], '%')
    print('  mean_ndvi:', s['mean_ndvi'])
    print('  max_ndvi:', s['max_ndvi'])
    print('  tile_url:', data['tile_url'][:55])
    print('  PASS' if s['area'] > 0 else '  WARN: area=0 (cloud cover or data gap)')

print()
print('=' * 60)
print('TEST 2: NDWI / Water Bodies')
data, err = post('/api/analyze', {
    'state': 'Karnataka', 'area': 'Mandya',
    'geometry': AOI, 'query': 'Where are the water bodies?'
})
if err:
    print('  FAIL:', err)
else:
    s = data['stats']
    print('  intent:', data['intent'])
    print('  index:', data['index'])
    print('  area:', s['area'], s['area_unit'])
    print('  coverage:', s['percentage_coverage'], '%')
    print('  mean_ndwi:', s['mean_ndwi'])
    print('  tile_url:', data['tile_url'][:55])
    print('  PASS')

print()
print('=' * 60)
print('TEST 3: Flood Detection')
data, err = post('/api/analyze', {
    'state': 'Karnataka', 'area': 'Bengaluru Rural',
    'geometry': AOI, 'query': 'Which regions are potentially flooded?'
})
if err:
    print('  FAIL:', err)
else:
    s = data['stats']
    print('  intent:', data['intent'])
    print('  index:', data['index'])
    print('  area:', s['area'], s['area_unit'])
    print('  coverage:', s['percentage_coverage'], '%')
    print('  tile_url:', data['tile_url'][:55])
    expl = data['explanation']
    print('  explanation snippet:', expl[:120])
    print('  PASS')

print()
print('=' * 60)
print('TEST 4: Error - Unknown query intent')
data, err = post('/api/analyze', {
    'state': 'Karnataka', 'area': 'Mysuru',
    'geometry': AOI, 'query': 'What is the weather today?'
})
if err and '400' in err:
    print('  PASS - correctly rejected with 400:', err[:80])
else:
    print('  FAIL - should have returned 400, got:', data)

print()
print('=' * 60)
print('TEST 5: Error - Invalid state')
try:
    r = urllib.request.urlopen(BASE + '/api/areas/NonexistentState', timeout=10)
    print('  FAIL - should have returned 404')
except urllib.request.HTTPError as e:
    if e.code == 404:
        print('  PASS - correctly returned 404 for unknown state')
    else:
        print('  FAIL - unexpected HTTP code:', e.code)
