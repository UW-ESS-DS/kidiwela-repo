import copy

from setup import *

if not package.valid:
  pytest.skip("Skipping data tests", allow_module_level=True)

def test_data_against_datapackage_json(max_values=100):
  if report['warnings']:
    print('Warnings [' + str(len(report['warnings'])) + ']')
    for warning in report['warnings']:
      print(warning)
  else:
    print('Warnings [none]')
  if report['valid']:
    print('Valid data [true]')
  else:
    for table in report['tables']:
      if table['valid']:
        print('Valid ' + table['source'] + ' [true]')
      else:
        print('Valid ' + table['source'] + ' [false]')
        # Truncate error values for printing
        errors = copy.deepcopy(table['errors'])
        for e in errors:
          data = e.get('message-data', {})
          if 'values' in data and len(data['values']) > max_values:
            data['values'] = data['values'][:max_values] + ['...']
        print(goodtables.json.dumps(errors, indent=2))
    print('Valid data [false]')
  assert report['valid']
