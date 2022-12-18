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

function quote(id) {
    var text = window.prompt('引用テキストを入力してください');
    if (text) {
        api_request('/api/quote?noteId=' + id + '&text=' + encodeURIComponent(text), function (status, body) {
            if (status == 200) {
                alert('投稿しました');
                location.reload();
            }
        });
    }
}