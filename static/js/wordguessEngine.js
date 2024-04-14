// consts
var MAX_LINES = 6;
var MAX_CHARS = 5;
// vars
var currentLine = 1;
var currentChar = 1;
var targetWord = '';
var inputWord = '';
var allowInput = false;
// 1 = GREEN , 2 = YELLOW, 3 = WHITE
var results = [
    [-1, -1, -1, -1, -1],
    [-1, -1, -1, -1, -1],
    [-1, -1, -1, -1, -1],
    [-1, -1, -1, -1, -1],
    [-1, -1, -1, -1, -1],
    [-1, -1, -1, -1, -1]
];
var gameClear = false;
var charAppearCount = {};
// DOMs
var inputResetButton = null;
var verifyButton = null;
var startButton = null;
var exitShareButton = null;

function changeScreen(screenId, callback) {
    var screens = document.getElementsByClassName('screen');
    for (var i = 0; i < screens.length; i++) {
        screens[i].style.display = 'none';
    }
    document.getElementById('screen_' + screenId).style.display = 'block';
    if (callback) callback();
}

function xhr(url, callback) {
    var x = new XMLHttpRequest();
    x.open('GET', url, true);
    x.onload = function () {
        callback(x);
    }
    x.send(null);
}

function setChar(line, num, char) {
    document.getElementById('char-' + line + '-' + num).innerHTML = char;
}

function registerKeyboardHandler() {
    var keys = document.getElementsByClassName('virtkey');
    for (var i = 0; i < keys.length; i++) {
        keys[i].onclick = function (ev) {
            if (!allowInput) return;
            if (currentChar > MAX_CHARS) {
                return;
            }
            if (currentChar > (MAX_CHARS - 1)) {
                verifyButton.disabled = false;
            } else {
                verifyButton.disabled = true;
            }
            var c = ev.target.getAttribute('data-key');
            setChar(currentLine, currentChar, c);
            inputWord = inputWord + c;
            if (currentChar === 1) inputResetButton.disabled = false;
            currentChar++;
        }
    }
}

function resetLine() {
    for (var c = 1; c <= MAX_CHARS; c++) {
        document.getElementById('char-' + currentLine + '-' + c).innerHTML = ' ';
    }
    inputWord = '';
    currentChar = 1;
}

function clearLineState(lineId) {
    for (var c = 1; c <= MAX_CHARS; c++) {
        var el = document.getElementById('char-' + lineId + '-' + c);
        classChange.remove(el, 'char-ok');
        classChange.remove(el, 'char-wrongpos');
        classChange.remove(el, 'char-ng');
    }
}

function activeLine(lineId) {
    var chars = document.getElementsByClassName('chars');
    for (var c = 0; c < chars.length; c++) {
        classChange.remove(chars[c], 'charline-active');
    }
    for (var x = 1; x <= MAX_CHARS; x++) {
        classChange.add(document.getElementById('char-' + lineId + '-' + x), 'charline-active');
    }
}

function mainControllerState(flag) {
    if (flag) {
        document.getElementById('main-exit').style.display = 'none';
        document.getElementById('main-controller').style.display = 'block';
    } else {
        document.getElementById('main-exit').style.display = 'block';
        document.getElementById('main-controller').style.display = 'none';
    }
}

function exitMain() {
    activeLine(1);
    for (var i = 1; i <= MAX_LINES; i++) {
        clearLineState(i);
    }
    for (var l = 1; l <= MAX_LINES; l++) {
        for (var c = 1; c <= MAX_CHARS; c++) {
            document.getElementById('char-' + l + '-' + c).innerHTML = ' ';
        }
    }
    inputWord = '';
    targetWord = '';
    currentLine = 1;
    currentChar = 1;
    allowInput = false;
    startButton.disabled = false;
    results = [
        [-1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1]
    ];
    gameClear = false;
    mainControllerState(true);
    changeScreen('title');
}

function verifyInputWord() {
    allowInput = false;
    verifyButton.disabled = true;

    var inputCharAppearCount = {};

    var okCount = 0;

    for (var i = 1; i <= MAX_CHARS; i++) {
        if (inputCharAppearCount[inputWord[i - 1]] === undefined) inputCharAppearCount[inputWord[i - 1]] = 0;
        inputCharAppearCount[inputWord[i - 1]]++;

        // 一致しないが
        if (inputWord[i - 1] !== targetWord[i - 1]) {
            // 文字がどこかに存在する かつ 出現回数の範囲内
            // charAppearCount[inputWord[i - 1]] : 全部の出現回数
            // inputCharAppearCount[inputWord[i - 1]] : 現在の出現回数
            isNotOverAppear = charAppearCount[inputWord[i - 1]] >= inputCharAppearCount[inputWord[i - 1]];
            charFound = targetWord.indexOf(inputWord[i - 1]) !== -1
            if (charFound && isNotOverAppear) {
                classChange.add(document.getElementById('char-' + currentLine + '-' + i), 'char-wrongpos');
                results[currentLine - 1][i - 1] = 2;
            } else {
            // 文字がどこにも存在しない (またはこれ以上その文字が出現しない)
                classChange.add(document.getElementById('char-' + currentLine + '-' + i), 'char-ng');
                results[currentLine - 1][i - 1] = 3;
            }
        } else{
        // 一致した
            okCount++;
            classChange.add(document.getElementById('char-' + currentLine + '-' + i), 'char-ok');
            results[currentLine - 1][i - 1] = 1;
        }
    }

    if (okCount === MAX_CHARS) {
        gameClear = true;
        mainControllerState(false);
        alert('クリア！');
        return;
    }

    if (currentLine >= MAX_LINES) {
        gameClear = false;
        mainControllerState(false);
        alert('ゲームオーバー\n正解は ' + targetWord);
        return;
    }

    allowInput = true;
    inputResetButton.disabled = true;
    currentLine++;
    currentChar = 1;
    inputWord = '';
    activeLine(currentLine);
}

window.addEventListener('DOMContentLoaded', function () {
    startButton = document.getElementById('w-btn-start');
    startButton.disabled = false;
    startButton.onclick = function () {
        startButton.disabled = true;
        xhr('/static/data/wordguess-word-list.json', function (req) {
            if (req.status !== 200) {
                alert('データを取得できませんでした (001)');
                return;
            }
            try {
                var words = JSON.parse(req.responseText);
            } catch (e) {
                alert('データを取得できませんでした (002)');
                return;
            }
            choice = words[Math.floor(Math.random() * words.length)];
            targetWord = choice.toUpperCase();
            // 文字ごとの出現回数をカウント(判定用)
            for (var charpos = 0; charpos < targetWord.length; charpos++) {
                if (charAppearCount[targetWord[charpos]] === undefined) charAppearCount[targetWord[charpos]] = 0;
                charAppearCount[targetWord[charpos]]++;
            }
            changeScreen('main', function () {
                allowInput = true;
            });
        });
    };

    inputResetButton = document.getElementById('w-btn-reset');
    inputResetButton.onclick = function () {
        if (!allowInput) return;
        resetLine();
        inputResetButton.disabled = true;
    };

    verifyButton = document.getElementById('w-btn-go');
    verifyButton.onclick = function () {
        if (!allowInput) return;
        verifyInputWord();
    };

    exitButton = document.getElementById('w-btn-exit');
    exitButton.onclick = function () {
        if (allowInput) return;
        exitMain();
    }

    exitShareButton = document.getElementById('w-btn-exit-share');
    exitShareButton.onclick = function () {
        var sharetext = 'Citraskey WordGuess ' + (gameClear ? currentLine : 'X') + '/' + MAX_LINES + '\n';
        for (var l = 1; l <= MAX_LINES; l++) {
            for (var c = 1; c <= MAX_CHARS; c++) {
                if (results[l - 1][c - 1] === -1) continue;
                sharetext += ['{unicode:GREEN_BLOCK}', '{unicode:YELLOW_BLOCK}', '{unicode:WHITE_BLOCK}'][results[l - 1][c - 1] - 1];
            }
            sharetext += '\n';
        }
        location.href = '/note-form?text=' + encodeURI(sharetext);
    }

    registerKeyboardHandler();
});