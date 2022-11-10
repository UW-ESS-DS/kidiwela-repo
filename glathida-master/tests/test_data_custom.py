from setup import *
import re
import datetime
import json
import urllib
import numpy as np
import pandas
import geopandas

if not package.valid or not report['valid']:
  pytest.skip("Skipping custom data tests", allow_module_level=True)

# ---- Fields not null by logical implication ----

# GLACIER_DB and GLACIER_ID either both null or both not null
def test_has_both_glacier_id_and_db():
  df = tables['t']
  np.testing.assert_array_equal(
    df['GLACIER_DB'].isna(),
    df['GLACIER_ID'].isna())

# *THICKNESS not null if *THICKNESS_UNCERTAINTY not null
checks = []
for resource in package.descriptor['resources']:
  for field in resource['schema']['fields']:
    if re.match('^.*THICKNESS$', field['name']):
      checks.append((resource['name'], field['name']))

@pytest.mark.parametrize('table, field', checks)
def test_has_thickness_if_uncertainty(table, field):
  df = tables[table]
  if re.match('^MAXIMUM_.*$', field):
    uncertainty = 'MAX_THICKNESS_UNCERTAINTY'
  else:
    uncertainty = field + '_UNCERTAINTY'
  mask = df[uncertainty].notna()
  assert df[mask][field].notna().all()

# *THICKNESS not null if DATA_FLAG not null
@pytest.mark.parametrize('table', ['t', 'tt', 'ttt'])
def test_has_thickness_if_flag(table):
  df = tables[table]
  mask = df['DATA_FLAG'].notna()
  if table in ('t', 'tt'):
    assert all(df[mask]['MEAN_THICKNESS'].notna() |
      df[mask]['MAXIMUM_THICKNESS'].notna())
  else:
    assert df[mask]['THICKNESS'].notna().all()

# SURVEY_METHOD_DETAILS not null if SURVEY_METHOD = 'OTH'
def test_has_details_if_survey_method_other():
  df = tables['t']
  mask = df['SURVEY_METHOD'] == 'OTH'
  assert df[mask]['SURVEY_METHOD_DETAILS'].notna().all()

# REMARKS not null if (GLACIER_DB, INTERPOLATION_METHOD) = 'OTH'
@pytest.mark.parametrize('field', ['GLACIER_DB', 'INTERPOLATION_METHOD'])
def test_has_remarks_if_field_other(field):
  df = tables['t']
  mask = df[field] == 'OTH'
  assert df[mask]['REMARKS'].notna().all()

 # (MEAN_THICKNESS, MAXIMUM_THICKNESS) not null if THICKNESS null
def test_has_thickness_estimates_if_no_thickness():
  df = tables['t']
  # MEAN_THICKNESS (TT, TTT) required
  mask = (~df['GlaThiDa_ID'].isin(tables['tt']['GlaThiDa_ID']) &
    ~df['GlaThiDa_ID'].isin(tables['ttt']['GlaThiDa_ID']))
  assert (df['MEAN_THICKNESS'][mask].notna() |
    df['MAXIMUM_THICKNESS'][mask].notna()).all()

# ---- Fields null by logical implication ----

# INTERPOLATION_METHOD null if (MEAN_THICKNESS, MAXIMUM_THICKNESS) null
def test_has_no_interpolation_method_if_no_thickness_estimates():
  df = tables['t']
  # TT.MEAN_THICKNESS required
  mask = (~df['GlaThiDa_ID'].isin(tables['tt']['GlaThiDa_ID']) &
    df['MEAN_THICKNESS'].isna() &
    df['MAXIMUM_THICKNESS'].isna())
  assert df['INTERPOLATION_METHOD'][mask].isna().all()

# ---- Custom field validation ----

# *_DATE exists
checks = []
for resource in package.descriptor['resources']:
  for field in resource['schema']['fields']:
    if re.match('^.*_DATE$', field['name']):
      checks.append((resource['name'], field['name']))

@pytest.mark.parametrize('table, field', checks)
def test_date_exists(table, field):
  ds = tables[table][field].drop_duplicates()
  mask = ds.notna()
  year = ds[mask].str[0:4].astype(int)
  month = ds[mask].str[4:6].astype(int)
  day = ds[mask].str[6:8].astype(int)
  today = datetime.datetime.today()
  # Year is before today
  assert all(year <= today.year)
  # Month is valid
  assert all((month == 99) | (month <= 12))
  this_year = year == today.year
  has_day = day < 99
  # Month is before today
  assert all(month[this_year & ~has_day] <= today.month)
  # Date exists
  dates = pandas.to_datetime(dict(
    year=year[has_day], month=month[has_day], day=day[has_day]))
  # Date before today
  assert all(dates <= today)

# GLACIER_ID matches GLACIER_DB pattern
# TODO: Replace with GLACIER_ID exists in GLACIER_DB
patterns = {
    'GLIMS': r'^G[0-9]{6}E[0-9]{5}N$',
    'RGI': r'^RGI(20|32|40|50|60)\-[0-1][0-9]\.[0-9]{5}$',
    'WGI': r'^[A-Z]{2}[0-9][A-Z][0-9A-Z]{8}$',
    'FOG': r'^[0-9]{,4}$'
}
@pytest.mark.parametrize('db', list(patterns.keys()))
def test_glacier_id_matches_db_pattern(db):
  df = tables['t']
  mask = df['GLACIER_DB'] == db
  assert df[mask]['GLACIER_ID'].str.match(patterns[db]).all()

# T.SURVEY_DATE first of multiple TT(T).SURVEY_DATE
@pytest.mark.parametrize('table', ['tt', 'ttt'])
def test_survey_date_first_if_multiple(table):
  df = tables[table]
  dates = df.groupby('GlaThiDa_ID')['SURVEY_DATE'].agg(['min'])
  surveys = tables['t'].set_index('GlaThiDa_ID').loc[dates.index]
  assert all(dates['min'].isna() | (dates['min'] == surveys.SURVEY_DATE))

# ---- Spatial constraints ----

# T.LAT, T.LON inside (or near) POLITICAL_UNIT
# NOTE: 30 km threshold allows four 'US' glaciers with origins in Canada
glaciers = geopandas.GeoDataFrame(tables['t'],
  geometry=geopandas.points_from_xy(tables['t']['LON'], tables['t']['LAT']),
  crs='epsg:4326')
country_codes = json.loads(urllib.request.urlopen(
  'https://github.com/mledoze/countries/raw/v2.1.0/countries.json').read())
A3_to_2 = {code['cca3']: code['cca2'] for code in country_codes}
# Country polygons use XKX for Kosovo, not UNK
A3_to_2['XKX'] = A3_to_2.pop('UNK')
countries = geopandas.read_file(
  'https://github.com/simonepri/geo-maps/releases/download/v0.6.0/countries-maritime-100m.geo.json')
# Self-touching or crossing polygons repaired with 0-distance buffer
# https://shapely.readthedocs.io/en/stable/manual.html#object.buffer
countries.geometry = countries.geometry.buffer(0)
countries['A2'] = [A3_to_2[code] for code in countries.A3]

@pytest.mark.parametrize('code', tables['t']['POLITICAL_UNIT'].unique())
def test_latlon_in_country(code):
  country = countries[countries['A2'] == code]
  mask = glaciers['POLITICAL_UNIT'] == code
  mask[mask] &= ~glaciers[mask].within(country.geometry.iloc[0])
  distances = [] # meters
  for i in range(mask.sum()):
    # Convert to local UTM zone to measure distance in meters
    glacier = glaciers[mask][i:i+1]
    zone = ((glacier.geometry.x.iloc[0] + 183) / 6).round().astype(int)
    crs = '+proj=utm +ellps=WGS84 +units=m +zone=' + str(zone)
    glacier_utm = glacier.to_crs(crs)
    country_utm = country.to_crs(crs)
    distances.append(glacier_utm.distance(country_utm.geometry.iloc[0]).iloc[0])
  assert all(np.array(distances) < 35e3)

# TTT.POINT_LAT, TTT.POINT_LON near T.LAT, T.LON
# NOTE: 110 km threshold allows for large glaciers in Antarctica
# TODO: Threshold by glacier length, estimated from glacier outline
def test_point_latlon_near_latlon():
  df = tables['ttt'][['GlaThiDa_ID', 'POINT_LAT', 'POINT_LON']].merge(
  tables['t'][['GlaThiDa_ID', 'LAT', 'LON']])
  radius = 6371e3 # Earth radius
  point_lat_rad = np.radians(df['POINT_LAT'])
  lat_rad = np.radians(df['LAT'])
  # Use great circle distance
  distances = radius * np.arccos(
    np.sin(point_lat_rad) * np.sin(lat_rad) +
    np.cos(point_lat_rad) * np.cos(lat_rad) *
    np.cos(np.radians(df['POINT_LON'] - df['LON'])))
  assert all(distances < 110e3)

# ---- Current state ----

# Optional fields not empty
exceptions = [('ttt', 'DATA_FLAG')]
checks = []
for resource in package.descriptor['resources']:
  for field in resource['schema']['fields']:
    if not field.get('constraints', {}).get('required', False):
      check = (resource['name'], field['name'])
      if check not in exceptions:
        checks.append(check)

@pytest.mark.parametrize('table, field', checks)
def test_optional_field_not_empty(table, field):
  df = tables[table]
  assert df[field].notna().any()

# ---- Unecessary duplication ----

# # REMARKS not all equal for each GlaThiDa_ID
# @pytest.mark.parametrize('table', ['tt', 'ttt'])
# def test_remarks_not_all_equal_for_survey(table):
#   df = tables[table]
#   values = df.groupby('GlaThiDa_ID')['REMARKS'].agg(
#     ['size', 'nunique', lambda x: x.isnull().sum()]).rename(
#     columns={'<lambda>': 'nnull'})
#   assert not any(
#     (values['size'] > 1) &
#     (values['nnull'] == 0) &
#     (values['nunique'] == 1))
