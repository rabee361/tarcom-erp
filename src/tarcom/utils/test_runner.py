from django.core.cache import cache
from django.test.runner import DiscoverRunner


class ThrottleAwareTestRunner(DiscoverRunner):
    """Flush the cache around every test so throttling cannot leak between them.

    DRF stores throttle counters in the cache, and that cache is shared for the
    whole run. Left alone, a suite making more requests than the anonymous
    budget within one sliding window starts failing with 429s that have nothing
    to do with what those tests assert.

    Only the boundary between tests is cleared; anything a single test sets up
    survives for that test, which is what tests like the dashboard lockout
    counter rely on.
    """

    def setUp(self, test, *args, **kwargs):
        super().setUp(test, *args, **kwargs)
        cache.clear()

    def tearDown(self, test, *args, **kwargs):
        cache.clear()
        super().tearDown(test, *args, **kwargs)
