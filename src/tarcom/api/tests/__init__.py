import os
import unittest

_MODULE_SUFFIX = '_tests.py'


def _test_module_names():
    package_dir = os.path.dirname(os.path.abspath(__file__))
    for filename in sorted(os.listdir(package_dir)):
        if filename.endswith(_MODULE_SUFFIX) and not filename.startswith('.'):
            yield f'{__name__}.{filename[:-len(".py")]}'


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(standard_tests)
    for module_name in _test_module_names():
        suite.addTests(loader.loadTestsFromName(module_name))
    return suite
