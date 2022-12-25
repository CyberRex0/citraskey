// ERROR ID
// 1000: note is deleted
// 1001: failed to renote
var ERROR_IDS = {
    1: '不明なエラー',
    1000: 'ノートが削除されています',
    1001: 'リノート操作に失敗しました',
    1002: 'ログインしていません',
    1003: 'パラメータが欠落しています',
    1004: 'レート制限中です。しばらくしてから再度お試しください',
    1005: 'ユーザーが見つかりません',
    1006: 'すでにピン留めされています',
    1007: 'リノート対象が見つかりません',
    1008: 'すでにフォローしています',
    1009: 'あなたはこのユーザーをブロックしています',
    1010: 'このユーザーはあなたをブロックしています',
    1011: 'すでにブロックしています',
    1012: 'すでにミュートしています',
    1013: 'すでに投票しています'
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

function api_request(url, callback, error_callback) {
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
            if (error_callback) {
                error_callback(xhr.status, xhr.responseText);
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
    api_request('/api/notes/renote?noteId=' + id, function (status, body) {
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
    xhr.open('GET', '/api/notes/undo_renote?noteId=' + id);
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
    var pickerContainerEl = document.getElementById('note-reaction-picker-container-' + noteId);
    pickerContainerEl.style.display = 'none';
    var presetPickerContainerEl = document.getElementById('note-reaction-picker-container-preset-' + noteId);
    presetPickerContainerEl.style.display = 'block';

    registerPickerReactionHandlerById(noteId);

    var searchBox = document.getElementById('note-reaction-picker-searchbox-' + noteId);
    var searchButton = document.getElementById('note-reaction-picker-searchbutton-' + noteId);

    searchButton.onclick = function (e) {
        var value = searchBox.value.trim();
        if (value) {
            api_request('/api/reaction/search?noteId=' + noteId + '&q=' + encodeURI(value), function (status, body) {
                if (status == 200) {
                    presetPickerContainerEl.style.display = 'none';
                    pickerContainerEl.style.display = 'block';
                    pickerContainerEl.innerHTML = body;
                    setInterval(function () { registerPickerReactionHandlerById(noteId) }, 500);
                }
            });
        }
    }

}

function fetchNote(note_id) {
    api_request('/api/notes/fetch?noteId=' + note_id, function (status, body) {
        if (status == 200) {
            var note = JSON.parse(body);
            return note;
        }
    });
}

function showSelectMenu(note_id) {
    var menuEl = document.getElementById('note-menu-' + note_id);
    menuEl.style.display = (menuEl.style.display=='none') ? 'inline' : 'none';
}

function toggleSearchBox() {
    var searchBoxEl = document.getElementById('searchbox');
    searchBoxEl.style.display = (searchBoxEl.style.display=='none') ? 'block' : 'none';
}

function confirmLogout() {
    if (window.confirm('ログアウトしますか？')) {
        location.href = '/logout';
    }
}

function actionFollowReq(action, userId) {
    var formEl = document.createElement('form');
    formEl.setAttribute('method', 'POST');
    formEl.setAttribute('action', '/api/i/follow-requests/' + action);
    var inputEl = document.createElement('input');
    inputEl.setAttribute('type', 'hidden');
    inputEl.setAttribute('name', 'userId');
    inputEl.setAttribute('value', userId);
    formEl.appendChild(inputEl);
    document.body.appendChild(formEl);
    formEl.submit();
}

function scrollToElement(el) {
    var clientRect = el.getBoundingClientRect();
    var px = window.pageXOffset + clientRect.left;
    var py = window.pageYOffset + clientRect.top;
    window.scrollTo(px, py);
}

function scrollToElementX(el) {
    var clientRect = el.getBoundingClientRect();
    var py = window.pageYOffset + clientRect.top;
    window.scrollTo(0, py);
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
        api_request('/api/notes/reaction?noteId=' + noteId + '&reaction=' + encodeURI(reaction) + '&type=' + reactionType, function (status, body) {
            if (status == 200) {
                document.getElementById(noteId + '-reactions').innerHTML = body;
                // DOM解析を待つ
                setInterval(function () { registerEmojiButtonHandlerByNoteId(noteId) }, 500);
            }
        });
    } else {
        api_request('/api/notes/reaction?noteId=' + noteId + '&reaction=&type=none', function (status, body) {
            if (status == 200) {
                document.getElementById(noteId + '-reactions').innerHTML = body;
                // DOM解析を待つ
                setInterval(function () { registerEmojiButtonHandlerByNoteId(noteId) }, 500);
            }
        });
    }
}

var emojiPickerButtonHandler = function (e) {
    var noteId = e.target.getAttribute('data-note-id');
    var reaction = e.target.getAttribute('data-reaction-content');
    var reaction_type = e.target.getAttribute('data-reaction-type');

    api_request('/api/notes/reaction?noteId=' + noteId + '&reaction=' + encodeURI(reaction) + '&type=' + reaction_type, function (status, body) {
        if (status == 200) {
            document.getElementById(noteId + '-reactions').innerHTML = body;
            document.getElementById('note-reaction-picker-' + noteId).style.display = 'none';
            // DOM解析を待つ
            setInterval(function () { registerEmojiButtonHandlerByNoteId(noteId) }, 500);
        }
    });
}

var noteMenuHandler = function (e) {
    var noteId = e.target.getAttribute('data-note-id');
    var selectedMenu = e.target.value;
    switch (selectedMenu) {
        case 'delete':
            if (window.confirm('本当に削除しますか？') === true) {
                api_request('/api/notes/delete?noteId=' + noteId, function (status, body) {
                    if (status == 200) {
                        var noteEl = document.getElementById('note-' + noteId);
                        noteEl.parentNode.removeChild(noteEl);
                        alert('投稿を削除しました。');
                    }
                });
            }
            break;
        
        case 'pin':
            api_request('/api/notes/pin?noteId=' + noteId, function (status, body) {
                if (status == 200) {
                    alert('ピン留めしました。');
                }
            });
            break;

        case 'unpin':
            if (window.confirm('本当にピン留めを解除しますか？') === true) {
                api_request('/api/notes/unpin?noteId=' + noteId, function (status, body) {
                    if (status == 200) {
                        alert('ピン留めを解除しました。');
                    }
                });
            }
            break;
        
        case 'report':
            var noteEl = document.getElementById('note-' + noteId);
            var userId = noteEl.getAttribute('data-user-id');
            var uri =  noteEl.getAttribute('data-note-remote-uri') || noteEl.getAttribute('data-note-uri');
            var content = window.prompt('通報理由を入力してください。');
            if (content && content.trim() != '') {
                var text = 'Note: ' + uri + '\n-----\n' + content.trim();
                api_request('/api/users/report?userId=' + userId + '&comment=' + encodeURI(text), function (status, body) {
                    if (status == 200) {
                        alert('通報しました。');
                    }
                });
            }
            break;
    }
    e.target.selectedIndex = 0;
}

var followButtonHandler = function (e) {
    var userId = e.target.getAttribute('data-user-id');
    var state = e.target.getAttribute('data-follow-state')==='true' ? true : false;
    var followBtnEl = document.getElementById('user-follow-button-' + userId);
    if (state) {
        api_request('/api/users/unfollow?userId=' + userId, function (status, body) {
            if (status == 200) {
                followBtnEl.innerHTML = 'フォロー';
                followBtnEl.setAttribute('data-follow-state', 'false');
            }
        });
    } else {
        api_request('/api/users/follow?userId=' + userId, function (status, body) {
            if (status == 200) {
                followBtnEl.innerHTML = 'フォロー解除';
                followBtnEl.setAttribute('data-follow-state', 'true');
            }
        });
    }
}

var userActionSelectHandler = function (e) {
    // USER_INFO は user_detail で埋め込んでいる
    var userId = USER_INFO.id;
    var selectedMenu = e.target.value;
    switch (selectedMenu) {
        case 'block':
            if (window.confirm('本当にブロックしますか？') === true) {
                api_request('/api/users/block?userId=' + userId, function (status, body) {
                    if (status == 200) {
                        alert('ブロックしました。');
                    }
                });
            }
            break;
        
        case 'unblock':
            if (window.confirm('本当にブロックを解除しますか？') === true) {
                api_request('/api/users/unblock?userId=' + userId, function (status, body) {
                    if (status == 200) {
                        alert('ブロックを解除しました。');
                    }
                });
            }
            break;
        
        case 'mute':
            if (window.confirm('本当にミュートしますか？') === true) {
                api_request('/api/users/mute?userId=' + userId, function (status, body) {
                    if (status == 200) {
                        alert('ミュートしました。');
                    }
                });
            }
            break;
        
        case 'unmute':
            if (window.confirm('本当にミュートを解除しますか？') === true) {
                api_request('/api/users/unmute?userId=' + userId, function (status, body) {
                    if (status == 200) {
                        alert('ミュートを解除しました。');
                    }
                });
            }
            break;
        
        case 'report':
            var content = window.prompt('通報理由を入力してください。');
            if (content && content.trim() != '') {
                var text = 'User: ' + USER_INFO.uri + '\n-----\n' + content.trim();
                api_request('/api/users/report?userId=' + userId + '&comment=' + encodeURI(text), function (status, body) {
                    if (status == 200) {
                        alert('通報しました。');
                    }
                });
            }
    }
    e.target.selectedIndex = 0;
}

var notePollChoiceHandler = function (e) {
    var noteId = e.target.getAttribute('data-note-id');
    var choiceIndex = e.target.getAttribute('data-choice-index');
    var pollAreaEl = document.getElementById('note-poll-' + noteId);

    if (window.confirm('投票しますか？')) {
        api_request('/api/notes/poll?noteId=' + noteId + '&index=' + choiceIndex, function (status, body) {
            if (status == 200) {
                pollAreaEl.innerHTML = body;
            }
        });
    } else {
        e.preventDefault();
    }
}

function messagingLinkHandler(e) {
    var userId = e.target.getAttribute('data-user-id');
    location.href = '/messaging/' + userId;
}

function registerPickerReactionHandlerById(noteId) {
    var pickerReactionButtons = document.getElementsByClassName('note-reaction-picker-child-' + noteId);
    for (var i = 0; i < pickerReactionButtons.length; i++) {
        pickerReactionButtons[i].onclick = emojiPickerButtonHandler;
    }
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

function registerNoteMenuHandler() {
    var noteMenus = document.getElementsByClassName('note-menu');
    for (var i = 0; i < noteMenus.length; i++) {
        noteMenus[i].onchange = noteMenuHandler;
    }
}

function registerFollowButtonHandler() {
    var followBtns = document.getElementsByClassName('user-follow-button');
    for (var i = 0; i < followBtns.length; i++) {
        followBtns[i].onclick = followButtonHandler;
    }
}

function registerUserActionSelectHandler() {
    var userActionSelects = document.getElementsByClassName('user-action-select');
    for (var i = 0; i < userActionSelects.length; i++) {
        userActionSelects[i].onchange = userActionSelectHandler;
    }
}

function registerNotePollChoiceHandler() {
    var notePollChoices = document.getElementsByClassName('note-poll-choice');
    for (var i = 0; i < notePollChoices.length; i++) {
        notePollChoices[i].onclick = notePollChoiceHandler;
    }
}

function registerMessagingLinkHandler() {
    var messagingLinks = document.getElementsByClassName('message-overview');
    for (var i = 0; i < messagingLinks.length; i++) {
        messagingLinks[i].onclick = messagingLinkHandler;
    }
}

window.addEventListener('load', function () {
    if (!document.getElementsByClassName) {
        alert('getElementsByClassName is not supported.');
        return;
    }
    registerEmojiButtonHandler();
    registerNoteMenuHandler();
    registerFollowButtonHandler();
    registerUserActionSelectHandler();
    registerNotePollChoiceHandler();
    registerMessagingLinkHandler();

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
