import requests

gage_id = "06719505"
url = 'http://localhost:8000/api/get_geopackage/geopackage/' + gage_id
results = requests.get(url)
results = results.text
print(results)
'''
url = 'http://127.0.0.1:8000/api/get_geopackage/get_parameters/'
payload = '{"gage_id": "06719505", "modules": ["CFE-S", "CFE-X"]}'
headers = {'Content-Type': 'application/json'}
results = requests.post(url, data=payload, headers=headers)
print(results.text)
'''
