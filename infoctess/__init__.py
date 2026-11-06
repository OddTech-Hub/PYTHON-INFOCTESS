# infoctess project package

# Compatibility patch for Python 3.14+ super() copy in Django BaseContext
try:
    import django.template.context as _ctx
    def _safe_basecontext_copy(self):
        obj = self.__class__.__new__(self.__class__)
        obj.dicts = self.dicts[:]
        return obj
    _ctx.BaseContext.__copy__ = _safe_basecontext_copy
except Exception:
    pass
