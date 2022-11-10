import pytest
import datapackage
import goodtables_pandas as goodtables

package = datapackage.Package('datapackage.json')
if package.valid:
  report, tables = goodtables.validate('datapackage.json', return_tables=True)
