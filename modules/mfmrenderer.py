from mfmpy import parser
from typing import Optional, Callable
import re
from .model import VNode
from .emojistore import EmojiStore
import html

_VALIDTIME_REGEX = re.compile(r'^[0-9.]+s$')
_LINEBREAK_REGEX = re.compile(r'(\r\n|\n|\r)')
_COLORCODE_REGEX = re.compile(r'^[0-9a-f]{3,6}$', re.I)

def __validTime(t: str):
    if not t:
        return None
    return t if _VALIDTIME_REGEX.match(t) else None

def _flatten(arr: list):
    a = []
    for ar in arr:
        if isinstance(ar, list):
            a.extend(ar)
        else:
            a.append(ar)
    return ''.join(a)

class BasicMFMRenderer:
    
    def __init__(self,
        emojiStore: Optional[EmojiStore] = None,
        emojiUrlFilter: Optional[Callable[[str], str]] = None,
        unicodeEmojiFilter: Optional[Callable[[str], str]] = None,
        author_host: Optional[str] = None,
        plain: Optional[bool] = None,
        nowrap: Optional[bool] = None,
        hashtag_url: Optional[str] = None,
        profile_url: Optional[str] = None
    ):
        self.plain: bool = plain
        self.nowrap: bool = nowrap
        self.hashtag_url: str = hashtag_url
        self.profile_url: str = profile_url
        self.emojistore: EmojiStore = emojiStore
        self.emojiUrlFilter: Optional[Callable[[str], str]] = emojiUrlFilter
        self.unicodeEmojiFilter: Optional[Callable[[str], str]] = unicodeEmojiFilter
        self.author_host: Optional[str] = author_host
    
    def render(self, text: str, _plain: Optional[bool] = None, _nowrap: Optional[bool] = None):
        plain = _plain or self.plain
        nowrap = _nowrap or self.nowrap
        if plain:
            vNode = parser.parseSimple(text)
        else:
            vNode = parser.parse(text)

        return _flatten([self.__genEl(e) for e in vNode])
    
    def __genEl(self, ast: VNode):
        if isinstance(ast, dict):
            ast = [ast]
        for token in ast:
            if token['type'] == 'text':
                text = _LINEBREAK_REGEX.sub('\n', token['props']['text'])
                if not self.plain:
                    res = []
                    for t in text.split('\n'):
                        res.append('<br>')
                        res.append(html.escape(t))
                    res.pop(0)
                    return res
                else:
                    return [html.escape(text.replace('\n', ' '))]

            if token['type'] == 'bold':
                return ['<b>' + _flatten(self.__genEl(token['children'])) + '</b>']
            
            if token['type'] == 'strike':
                return ['<del>' + _flatten(self.__genEl(token['children'])) + '</del>']
            
            if token['type'] == 'italic':
                return ['<i style="font-style: oblique;">' + _flatten(self.__genEl(token['children'])) + '</i>']
            
            if token['type'] == 'fn':
                style = ''
                if token['props']['name'] == 'tada':
                    style = 'font-size: 130%;'
                
                if token['props']['name'] == 'jelly':
                    pass
                
                if token['props']['name'] == 'twitch':
                    pass
                
                if token['props']['name'] == 'shake':
                    pass
                
                if token['props']['name'] == 'spin':
                    pass
                
                if token['props']['name'] == 'jump':
                    pass
                
                if token['props']['name'] == 'bounce':
                    pass

                if token['props']['name'] == 'flip':
                    pass
                
                if token['props']['name'] == 'x2':
                    return ['<span style="font-size: 1.3em">' + _flatten(self.__genEl(token['children'])) + '</span>']
                
                if token['props']['name'] == 'x3':
                    return ['<span style="font-size: 1.6em">' + _flatten(self.__genEl(token['children'])) + '</span>']
                
                if token['props']['name'] == 'x4':
                    return ['<span style="font-size: 1.9em">' + _flatten(self.__genEl(token['children'])) + '</span>']
                
                if token['props']['name'] == 'font':
                    pass

                if token['props']['name'] == 'blur':
                    pass
                
                if token['props']['name'] == 'rainbow':
                    pass

                if token['props']['name'] == 'sparkle':
                    return _flatten(self.__genEl(token['children']))

                if token['props']['name'] == 'rotate':
                    pass

                if token['props']['name'] == 'position':
                    pass
                
                if token['props']['name'] == 'fg':
                    color = token['props']['args']['color']
                    if _COLORCODE_REGEX.match(color):
                        style = f'color: #{color}'

                if token['props']['name'] == 'bg':
                    color = token['props']['args']['color']
                    if _COLORCODE_REGEX.match(color):
                        style = f'background-color: #{color}'

                if not style:
                    els = ['$[', token['props']['name'], ' ']
                    els.extend(list(map(self.__genEl, token['children'])))
                    els.append(']')
                    return ['<span>' + _flatten(els) + '</span>']
                else:
                    return ['<span style="display: inline-block">' + _flatten(self.__genEl(token['children']))+ '</span>']
            
            if token['type'] == 'small':
                return ['<small>' + _flatten(self.__genEl(token['children'])) + '</small>']
            
            if token['type'] == 'center':
                return ['<center>' + _flatten(self.__genEl(token['children'])) + '</center>']
            
            if token['type'] == 'url':
                return ['<a href="' + token['props']['url'] + '">' + token['props']['url'] + '</a>']
            
            if token['type'] == 'link':
                pass

            if token['type'] == 'mention':
                uname = token['props']['username'] + ('@' + token['props']['host'] if token['props']['host'] else '')
                if self.profile_url:
                    return ['<a href="' + self.profile_url + uname + '">@' + uname + '</a>']
                else:
                    return ['@'+ uname]
            
            if token['type'] == 'hashtag':
                if self.profile_url:
                    return ['<a href="' + self.hashtag_url + token['props']['hashtag'] + '">#' + token['props']['hashtag'] + '</a>']
                else:
                    return ['#' + token['props']['hashtag']]
            
            if token['type'] == 'blockCode':
                return ['<pre style="display: block">\n' + token['props']['code'] + '\n</pre>']
            
            if token['type'] == 'inlineCode':
                return ['<pre style="display: inline">' + token['props']['code'] + '</pre>']
            
            if token['type'] == 'quote':
                if not self.nowrap:
                    return ['<div class="mfm-quote">' + _flatten(self.__genEl(token['children'])) + '</div>']
                else:
                    return ['<span class="mfm-quote">' + _flatten(self.__genEl(token['children'])) + '</span>']
            
            if token['type'] == 'emojiCode':
                emoji_name = token['props']['name']
                emoji_host = self.author_host
                emoji = self.emojistore.get(emoji_host, emoji_name)
                if emoji:
                    if self.emojiUrlFilter:
                        return ['<img class="mfm-custom-emoji" src="' + self.emojiUrlFilter(emoji['url']) + '">']
                    else:
                        return ['<img class="mfm-custom-emoji" src="' + emoji['url'] + '">']
            
            if token['type'] == 'unicodeEmoji':
                if self.unicodeEmojiFilter:
                    return [self.unicodeEmojiFilter(token['props']['emoji'])]
                else:
                    return [token['props']['emoji']]

            if token['type'] == 'plain':
                return ['<span>' + _flatten(self.__genEl(token['children'])) + '</span>']
            
            return []
            
    