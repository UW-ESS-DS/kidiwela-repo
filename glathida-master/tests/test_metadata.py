from setup import *

def test_datapackage_json():
    if not package.valid:
        for error in package.errors:
            print(error)
    assert package.valid
