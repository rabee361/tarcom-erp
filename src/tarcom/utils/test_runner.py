from unittest import TextTestResult

from django.core.cache import cache
from django.test.runner import DiscoverRunner


class _CacheFlushingResultMixin:
    """Flush the shared cache before and after each test.

    DRF stores throttle counters in the cache, and that cache is shared for the
    whole run. Left alone, a suite making more requests than the anonymous
    budget within one sliding window starts failing with 429s that have nothing
    to do with what those tests assert.

    Only the boundary between tests is cleared; anything a single test sets up
    survives for that test, which is what tests like the dashboard lockout
    counter rely on.
    """

    def startTest(self, test):
        cache.clear()
        super().startTest(test)

    def stopTest(self, test):
        cache.clear()
        super().stopTest(test)


class ThrottleAwareTestRunner(DiscoverRunner):
    # DiscoverRunner has no per-test setUp/tearDown hooks to override, so the
    # flush is installed through the result object, whose startTest/stopTest
    # run around every test.
    def get_resultclass(self):
        base = super().get_resultclass() or TextTestResult
        return type(f"CacheFlushing{base.__name__}", (_CacheFlushingResultMixin, base), {})
