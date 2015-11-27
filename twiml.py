import copy

from lxml.builder import E
from lxml.etree import tounicode

from operator import methodcaller

# relatively little overhead, because C <3
toxml = lambda iterable: list(map(methodcaller('toxml'), iterable))


class Container:
    def __init__(self, contents=None):
        self.contents = contents or []

    def add(self, node):
        self.contents.append(node)
        return self

    def toxml(self):
        return toxml(self.contents)


class Gather(Container):
    NODE = E.Gather

    def __init__(self, root, numDigits, action, contents=None):
        self._root = root
        self.numDigits = numDigits
        self.action = action
        super().__init__(contents)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def say(self, text, language=None):
        return self.add(self._root._classes['say'](
            self._root,
            text=text,
            language=language
        ))

    def toxml(self):
        return Gather.NODE(
            *super().toxml(),
            action=self.action,
            numDigits=self.numDigits
        )


class Say:
    NODE = E.Say

    def __init__(self, _root, text, **kwargs):
        self._root = _root
        self.text = text
        self.kwargs = kwargs

    def toxml(self):
        return Say.NODE(self.text, **self._root.merge_globals(self.kwargs))


class Pause:
    NODE = E.Pause

    def __init__(self, length):
        self.length = length

    def toxml(self):
        return Pause.NODE(length=str(self.length))


class Hangup:
    NODE = E.Hangup

    def toxml(self):
        return Hangup.NODE()


class Response(Container):
    NODE = E.Response

    def __init__(self):
        self._classes = {
            'gather': Gather,
            'say': Say,
            'pause': Pause,
            'hangup': Hangup
        }
        self.globals = {'language': 'en-AU'}
        super().__init__()

    def say(self, text, language=None):
        return self.add(self._classes['say'](
            self,
            text=text, language=language
        ))

    def pause(self, length):
        return self.add(self._classes['pause'](length=length))

    def hangup(self):
        return self.add(self._classes['hangup']())

    def toxml(self):
        root = Response.NODE(*super().toxml())

        prefix = '<?xml version="1.0" encoding="UTF-8"?>'
        return prefix + tounicode(root)

    def gather(self, numDigits=None, action=None):
        res = self._classes['gather'](
            self, numDigits=numDigits, action=action
        )
        self.add(res)
        return res

    def merge_globals(self, specific):
        specific = {
            key: val
            for key, val in specific.items()
            if val is not None
        }
        return dict(copy.deepcopy(self.globals), **specific)
