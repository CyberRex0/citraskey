// ERROR ID
// 1000: note is deleted
// 1001: failed to renote
var ERROR_IDS = {
    1: '不明なエラー',
    1000: 'ノートが削除されています',
    1001: 'リノート操作に失敗しました',
    1002: 'ログインしていません',
    1003: 'パラメータが欠落しています',
    1004: 'レート制限中です。しばらくしてから再度お試しください'
}

var NOTE_VISIBILITY = {
    public: 0,
    home: 1,
    followers: 2
}

function noteContentVToggle(id) {
    var noteContent = document.getElementById('note-content-' + id);
    noteContent.style.display = (noteContent.style.display=='none') ? 'block' : 'none';
}


function api_request(url, callback) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url);
    xhr.onload = function () {
        if (xhr.status == 200) {
            callback(xhr.status, xhr.responseText);
        } else {
            try{
                var error = JSON.parse(xhr.responseText);
                if (error.errorId != 1) {
                    alert('エラー ' + error.errorId + '\n' + ERROR_IDS[error.errorId]);
                } else {
                    alert('エラー\n' + error.reason);
                }
            } catch (e) {
                alert('API Request failed!\n' + xhr.responseText);
            }
            throw new Error(xhr.status);
        }
    }
    xhr.send();
}

function do_renote(e, id) {
    try {
        do_renote2(e, id);
    } catch (e) {
        alert(e);
    }
}

function do_renote2(e, id) {
    var xhr = new XMLHttpRequest();
    api_request('/api/renote?noteId=' + id, function (status, body) {
        if (status == 200) {
            e.innerHTML = 'リノートしました';
            e.disabled = true;
            setTimeout(function () {
                e.innerHTML = 'リノート取り消し';
                e.disabled = false;
                e.onclick = function (e) {
                    undo_renote(e.target, id);
                };
            }, 2000);
        }
    });
}

function undo_renote(e, id) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/undo_renote?noteId=' + id);
    xhr.onload = function () {
        if (xhr.status == 200) {
            e.innerHTML = 'リノート解除しました';
            e.disabled = true;
            setTimeout(function () {
                e.innerHTML = 'リノート';
                e.disabled = false;
                e.onclick = function (e) {
                    do_renote(e.target , id);
                };
            }, 2000);
        } else if (xhr.status == 404) {
            alert('リノートはすでに解除されています');
            e.innerHTML = 'リノート';
            e.disabled = false;
            e.onclick = function (e) {
                do_renote(e.target, id);
            };
        } else if (xhr.status == 400) {
            alert(xhr.responseText);
        } else {
            alert('リノート操作に失敗しました');
        }
    }
    xhr.send();
}

function quote(id, visibility, localOnly) {
    document.getElementById('note-form-reply-id').value = '';
    document.getElementById('note-form-reply-head').style.display = 'none';

    document.getElementById('note-form-note-id').value = id;
    document.getElementById('note-form-input-text').focus();
    document.getElementById('note-form-select-visibility').selectedIndex = NOTE_VISIBILITY[visibility];
    document.getElementById('nf_localonly').checked = localOnly;
    document.getElementById('note-form-submit').value = '引用ノート';
    document.getElementById('note-form-quote-cancel').onclick = function () {
        loadNoteFromConfig();
        document.getElementById('note-form-note-id').value = '';
        document.getElementById('note-form-input-text').innerHTML = '';
        document.getElementById('note-form-submit').value = 'ノート';
        document.getElementById('note-form-quote-head').style.display = 'none';
        scrollToElement(document.getElementById('note-' + id));
    }
    document.getElementById('note-form-quote-head').style.display = 'block';
}

function reply(id, visibility, localOnly) {
    document.getElementById('note-form-note-id').value = '';
    document.getElementById('note-form-quote-head').style.display = 'none';

    document.getElementById('note-form-reply-id').value = id;
    document.getElementById('note-form-input-text').focus();
    document.getElementById('note-form-select-visibility').selectedIndex = NOTE_VISIBILITY[visibility];
    document.getElementById('nf_localonly').checked = localOnly;
    document.getElementById('note-form-submit').value = '返信';
    document.getElementById('note-form-reply-cancel').onclick = function () {
        loadNoteFromConfig();
        document.getElementById('note-form-reply-id').value = '';
        document.getElementById('note-form-input-text').innerHTML = '';
        document.getElementById('note-form-submit').value = 'ノート';
        document.getElementById('note-form-reply-head').style.display = 'none';
        scrollToElement(document.getElementById('note-' + id));
    }
    document.getElementById('note-form-reply-head').style.display = 'block';
}

function reaction(noteId) {
    var pickerEl = document.getElementById('note-reaction-picker-' + noteId);
    pickerEl.style.display = (pickerEl.style.display=='none') ? 'block' : 'none';

    var presetReactionButtons = document.getElementsByClassName('note-reaction-preset-' + noteId);
    for (var i = 0; i < presetReactionButtons.length; i++) {
        presetReactionButtons[i].onclick = presetEmojiButtonHandler;
    }
}

function scrollToElement(el) {
    var clientRect = el.getBoundingClientRect();
    var px = window.pageXOffset + clientRect.left;
    var py = window.pageYOffset + clientRect.top;
    window.scrollTo(px, py);
}

function loadNoteFromConfig() {

}

var emojiButtonHandler = function (e) {
    var targetReactionId = e.target.getAttribute('data-reaction-element-id');
    var targetReactionEl = document.getElementById('note-reaction-element-' + targetReactionId);
    var noteId = targetReactionEl.getAttribute('data-note-id');
    var reaction = targetReactionEl.getAttribute('data-reaction-content');
    var reactionType = targetReactionEl.getAttribute('data-reaction-type');
    if (reactionType == 'custom') {
        reaction = ':' + reaction + ':';
    }
    var reactionElRootId = targetReactionEl.getAttribute('data-reaction-element-root');
    var reactionRootEl =  e.target; // document.getElementById('note-reaction-element-root-' + reactionElRootId);
    //alert('noteId: ' + noteId + '\n' + 'reaction: ' + reaction + '\n' + 'reactionType: ' + reactionType);
    if (reactionRootEl.className.indexOf('note-reaction-selected') === -1) {
        api_request('/api/reaction?noteId=' + noteId + '&reaction=' + encodeURI(reaction) + '&type=' + reactionType, function (status, body) {
            if (status == 200) {
                document.getElementById(noteId + '-reactions').innerHTML = body;
                // DOM解析を待つ
                setInterval(function () { registerEmojiButtonHandlerByNoteId(noteId) }, 500);
            }
        });
    } else {
        api_request('/api/reaction?noteId=' + noteId + '&reaction=&type=none', function (status, body) {
            if (status == 200) {
                document.getElementById(noteId + '-reactions').innerHTML = body;
                // DOM解析を待つ
                setInterval(function () { registerEmojiButtonHandlerByNoteId(noteId) }, 500);
            }
        });
    }
}

var presetEmojiButtonHandler = function (e) {
    var noteId = e.target.getAttribute('data-note-id');
    var reaction = e.target.getAttribute('data-reaction');

    api_request('/api/reaction?noteId=' + noteId + '&reaction=' + encodeURI(reaction) + '&type=unicode', function (status, body) {
        if (status == 200) {
            document.getElementById(noteId + '-reactions').innerHTML = body;
            document.getElementById('note-reaction-picker-' + noteId).style.display = 'none';
            // DOM解析を待つ
            setInterval(function () { registerEmojiButtonHandlerByNoteId(noteId) }, 500);
        }
    });
}

function registerEmojiButtonHandler() {
    var customEmojiBtns = document.getElementsByClassName('reactive-emoji');
    for (var i = 0; i < customEmojiBtns.length; i++) {
        customEmojiBtns[i].onclick = emojiButtonHandler;
    }
}

function registerEmojiButtonHandlerByNoteId(noteId) {
    var emojiBtns = document.getElementsByClassName('note-reaction-button-' + noteId);
    for (var i = 0; i < emojiBtns.length; i++) {
        emojiBtns[i].onclick = emojiButtonHandler;
    }
}

window.addEventListener('load', function () {
    if (!document.getElementsByClassName) {
        alert('getElementsByClassName is not supported.');
        return;
    }
    registerEmojiButtonHandler();

    var noteFormVisibility = document.getElementById('note-form-select-visibility');
    var noteFormLocalOnly = document.getElementById('nf_localonly');

    if (noteFormVisibility) {
        noteFormVisibility.onchange = function (e) { Cookies.set('note-form-visibility', e.target.value); }
        if (Cookies.get('note-form-visibility')) {
            noteFormVisibility.selectedIndex = NOTE_VISIBILITY[Cookies.get('note-form-visibility')];
        }
    }
    if (noteFormLocalOnly) {
        noteFormLocalOnly.onchange = function (e) { Cookies.set('note-form-localonly', e.target.checked); }
        if (Cookies.get('note-form-localonly')) {
            noteFormLocalOnly.checked = Cookies.get('note-form-localonly') === 'true';
        }
    }

    var noteFormWaitScreen = document.getElementById('note-form-wait-screen');
    if (noteFormWaitScreen) {
        noteFormWaitScreen.style.display = 'none';
    }

});
