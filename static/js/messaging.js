var pollTimer = null;

function pollNewMessage() {
    try {
        api_request('/api/users/messaging/messages?userId=' + MESSAGING_CONFIG.senderId + (MESSAGING_CONFIG.lastMessageId!='' ? '&lastId='+MESSAGING_CONFIG.lastMessageId : ''), function (status, body) {
            var res = JSON.parse(body);
            if (res.updated === true) {
                var messagesEl = document.getElementById('messages');
                messagesEl.innerHTML = res.html + messagesEl.innerHTML;
                MESSAGING_CONFIG.lastMessageId = res.lastMessageId;
            }
        }, function () { clearInterval(pollTimer) });
    } catch (e) {
        clearInterval(pollTimer);
    }
}

window.addEventListener('load', function () {
    pollTimer = setInterval(pollNewMessage, 5000);
});