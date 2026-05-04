document.addEventListener("DOMContentLoaded", () => {
    /* =========================================
       GLOBAL STATE / VARIABLES
    ========================================= */

    let connectedUser = null;
    let selectedFile = null;
    let allUsers = [];

    let receivedChunks = [];
    let currentFileName = "";

    let isCancelled = false;
    let receivedSize = 0;
    let totalFileSize = 0;

    let connectedUsers = new Set();

    // Sender variables
    let file = null;
    let offset = 0;
    const chunkSize = 128 * 1024;
    const reader = new FileReader();

    // Socket
    const socket = io();


    /* =========================================
       SOCKET CONNECTION
    ========================================= */

    socket.on('connect', () => {
        console.log("Connected to server");
    });


    /* =========================================
       CORE FUNCTIONS
    ========================================= */
    const SECRET = "my-very-strong-secret-key-123";

    // convert string → CryptoKey
    async function getKey() {
        const enc = new TextEncoder();
        const keyMaterial = await crypto.subtle.digest("SHA-256", enc.encode(SECRET));

        return crypto.subtle.importKey(
            "raw",
            keyMaterial,
            { name: "AES-GCM" },
            false,
            ["encrypt", "decrypt"]
        );
    }



    function readNextChunk() {

        if (isCancelled) {
            console.log("Transfer stopped due to cancel");
            return;
        }

        const slice = file.slice(offset, offset + chunkSize);

        const isLastChunk = offset + chunkSize >= file.size;

        reader.onload = async (e) => {

            const rawData = e.target.result;
            const key = await getKey();

            const iv = crypto.getRandomValues(new Uint8Array(12));

            const encrypted = await crypto.subtle.encrypt(
                { name: "AES-GCM", iv: iv },
                key,
                rawData
            );

            const bytes = new Uint8Array(encrypted);
            let binary = "";

            for (let i = 0; i < bytes.length; i++) {
                binary += String.fromCharCode(bytes[i]);
            }

            const encryptedChunk = btoa(binary);

            let ivBinary = "";
            for (let i = 0; i < iv.length; i++) {
                ivBinary += String.fromCharCode(iv[i]);
            }

            const ivString = btoa(ivBinary);

            socket.emit('file_chunk', {
                fileName: file.name,
                chunk: encryptedChunk,
                iv: ivString,
                to: connectedUser,
                from: currentUsername,
                isLast: isLastChunk,
                totalSize: file.size
            });

            let percent = Math.floor((offset / file.size) * 100);

            const bar = document.getElementById("progressBar");
            bar.style.width = percent + "%";
            bar.innerText = percent + "%";

            document.getElementById("statusText").innerText = "Sending...";
        };

        reader.readAsArrayBuffer(slice);

        offset += chunkSize;
    }


    function renderUsers(users) {
        const list = document.getElementById("usersList");
        list.innerHTML = "";

        users.forEach(user => {

            if (user === currentUsername) return;

            const li = document.createElement("li");
            li.className = "list-group-item";

            // 🔥 MAIN CONTAINER
            const container = document.createElement("div");
            container.className = "d-flex justify-content-between align-items-center";

            // 🔹 LEFT SIDE (Avatar + Name)
            const leftDiv = document.createElement("div");
            leftDiv.className = "d-flex align-items-center";

            // Avatar
            const avatar = document.createElement("div");
            avatar.className = "bg-primary text-white rounded-circle d-flex justify-content-center align-items-center me-2";
            avatar.style.width = "35px";
            avatar.style.height = "35px";
            avatar.innerText = user.charAt(0).toUpperCase();

            // Name + Status
            const textDiv = document.createElement("div");

            const name = document.createElement("div");
            name.innerText = user;

            const status = document.createElement("small");

            status.className = connectedUsers.has(user) ? "user-status" : "user-online";

            status.innerText = connectedUsers.has(user) ? "● Connected" : "● Online";

            textDiv.appendChild(name);
            textDiv.appendChild(status);

            leftDiv.appendChild(avatar);
            leftDiv.appendChild(textDiv);

            // 🔹 RIGHT SIDE (Buttons)
            const btnContainer = document.createElement("div");

            if (connectedUsers.has(user)) {

                // Send Button
                const sendBtn = document.createElement("button");
                sendBtn.innerText = "Send";
                sendBtn.className = "btn btn-sm btn-primary me-2";

                sendBtn.onclick = () => {
                    connectedUser = user;
                    document.getElementById("fileInput").click();
                };

                // Disconnect Button
                const disconnectBtn = document.createElement("button");
                disconnectBtn.innerText = "Disconnect";
                disconnectBtn.className = "btn btn-sm btn-danger";

                disconnectBtn.onclick = () => {
                    socket.emit("disconnect_user", { to: user });
                };

                btnContainer.appendChild(sendBtn);
                btnContainer.appendChild(disconnectBtn);

            } else {
                const connectBtn = document.createElement("button");
                connectBtn.innerText = "Connect";
                connectBtn.className = "btn btn-sm btn-success";

                connectBtn.onclick = () => {
                    socket.emit('send_request', { to: user });
                };

                btnContainer.appendChild(connectBtn);
            }

            container.appendChild(leftDiv);
            container.appendChild(btnContainer);

            li.appendChild(container);
            list.appendChild(li);
        });
    }


    /* =========================================
       UI HANDLERS
    ========================================= */

    document.getElementById("fileInput").onchange = (e) => {
        file = e.target.files[0];

        if (!file || !connectedUser) return;

        selectedFile = file;
        document.getElementById("fileInfo").innerText = file.name;

        document.getElementById("progressBar").style.width = "0%";
        document.getElementById("progressBar").innerText = "0%";
        document.getElementById("statusText").innerText = "Waiting for receiver...";

        alert("File selected: " + file.name);

        socket.emit('file_send_request', {
            fileName: file.name,
            to: connectedUser,
            totalSize: file.size   // 🔥 ADD THIS
        });

        document.getElementById("fileInput").value = "";
    };


    document.getElementById("cancelBtn").addEventListener("click", () => {

        isCancelled = true;

        document.getElementById("cancelBtn").classList.add("d-none");

        socket.emit("cancel_transfer", {
            to: connectedUser
        });

        document.getElementById("statusText").innerText = "❌ Transfer Cancelled";

        const bar = document.getElementById("progressBar");
        bar.classList.remove("progress-bar-animated");
        bar.classList.add("bg-danger");
    });

    function showToast(message, type = "dark") {
        const toastEl = document.getElementById("liveToast");
        const toastMsg = document.getElementById("toastMessage");

        // reset classes
        toastEl.className = `toast align-items-center text-bg-${type} border-0`;

        toastMsg.innerText = message;

        const toast = new bootstrap.Toast(toastEl);
        toast.show();
    }
    /* =========================================
       SOCKET EVENTS
    ========================================= */

    // USERS
    socket.on('update_users', (users) => {
        allUsers = users;
        renderUsers(users);

        const statusEl = document.getElementById("status");
        const usernameEl = document.getElementById("username");

        if (!statusEl || !usernameEl) return;

        const currentUser = usernameEl.innerText;

        if (users.includes(currentUser)) {
            statusEl.innerText = "Online";
            statusEl.className = "badge bg-success";
        } else {
            statusEl.innerText = "Offline";
            statusEl.className = "badge bg-secondary";
        }
    });


    // CONNECTION REQUEST
    socket.on('receive_request', (data) => {
        console.log("RECEIVED REQUEST:", data);

        const sender = data.from;

        const accept = confirm(`User ${sender} wants to connect. Accept?`);

        if (accept) {
            socket.emit('accept_request', { to: sender });
        } else {
            socket.emit('reject_request', { to: sender });
        }
    });


    // CONNECTION STATUS
    socket.on('request_accepted', (data) => {
        const user = data.from;

        console.log("🔥 ACCEPT EVENT:", user);

        // 1. update state
        connectedUsers.add(user);

        // 2. update UI FIRST
        renderUsers(allUsers);

        // 3. show toast AFTER UI settles
        setTimeout(() => {
            showToast(`Connected with ${user} ✅`, "success");
        }, 100);
    });


    socket.on('request_rejected', () => {
        showToast("Request rejected ❌", "danger");
    });


    // FILE REQUEST
    socket.on('incoming_file', (data) => {

        // RESET BEFORE START
        receivedChunks = [];
        receivedSize = 0;
        totalFileSize = data.totalSize;
        document.getElementById("fileInfo").innerText = data.fileName;
        document.getElementById("statusText").innerText = "Incoming file...";
        const accept = confirm(`${data.from} wants to send ${data.fileName}. Accept?`);

        if (accept) {
            socket.emit('file_accept', { to: data.from });
        } else {
            socket.emit('file_reject', { to: data.from });
        }
    });


    // START TRANSFER
    socket.on('start_file_transfer', () => {

        if (!selectedFile) {
            alert("No file selected!");
            return;
        }

        document.getElementById("fileInfo").innerText = selectedFile.name;

        isCancelled = false;
        document.getElementById("cancelBtn").classList.remove("d-none");

        file = selectedFile;
        offset = 0;

        readNextChunk();
    });


    // RECEIVE FILE (FULL)
    socket.on('receive_file', (data) => {

        const blob = new Blob([data.fileData]);
        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = data.fileName;
        a.click();
    });


    // RECEIVE CHUNK
    socket.on('receive_chunk', async (data) => {

        const key = await getKey();

        // decode base64 → bytes
        const encryptedBytes = Uint8Array.from(atob(data.chunk), c => c.charCodeAt(0));
        const iv = Uint8Array.from(atob(data.iv), c => c.charCodeAt(0));

        const decrypted = await crypto.subtle.decrypt(
            { name: "AES-GCM", iv: iv },
            key,
            encryptedBytes
        );

        const byteArray = new Uint8Array(decrypted);

        receivedChunks.push(byteArray);
        currentFileName = data.fileName;


        totalFileSize = data.totalSize || 0;


        receivedSize += byteArray.length;

        socket.emit('ack_chunk', {
            to: data.from
        });

        let percent = 0;

        if (totalFileSize > 0) {
            percent = Math.floor((receivedSize / totalFileSize) * 100);
        }

        const bar = document.getElementById("progressBar");
        bar.style.width = percent + "%";
        bar.innerText = percent + "%";
        bar.offsetHeight;

        document.getElementById("statusText").innerText = "Receiving...";

        if (data.isLast) {

            const blob = new Blob(receivedChunks);
            const url = URL.createObjectURL(blob);

            const a = document.createElement("a");
            a.href = url;
            a.download = currentFileName;
            a.click();

            // ✅ SHOW FILE NAME FIRST
            document.getElementById("fileInfo").innerText = currentFileName;

            // reset AFTER
            receivedChunks = [];
            currentFileName = "";
            selectedFile = null;
            totalFileSize = 0;
            receivedSize = 0;

            document.getElementById("statusText").innerText = "File received successfully ✅";

            bar.style.width = "100%";
            bar.innerText = "100%";
        }
    });


    // NEXT CHUNK
    socket.on('next_chunk', () => {

        if (isCancelled) {
            console.log("Stopped next_chunk due to cancel");
            return;
        }

        if (offset < file.size) {
            readNextChunk();
        } else {

            const bar = document.getElementById("progressBar");

            bar.style.width = "100%";
            bar.innerText = "100%";

            document.getElementById("statusText").innerText = "File sent successfully ✅";
            document.getElementById("fileInfo").innerText = file.name;

            document.getElementById("cancelBtn").classList.add("d-none");

            selectedFile = null;
            file = null;
        }
    });


    // TRANSFER CANCELLED
    socket.on("transfer_cancelled", () => {

        document.getElementById("cancelBtn").classList.add("d-none");

        receivedChunks = [];
        receivedSize = 0;
        totalFileSize = 0;

        document.getElementById("statusText").innerText = "❌ Transfer Cancelled by sender";

        const bar = document.getElementById("progressBar");
        bar.classList.remove("progress-bar-animated");
        bar.classList.add("bg-danger");
    });


    // RESTORE CONNECTIONS
    socket.on('restore_connections', (users) => {

        users.forEach(user => {
            connectedUsers.add(user);
        });

        renderUsers(allUsers);
    });

    socket.on("user_disconnected", (data) => {

        console.log("🔥 DISCONNECT EVENT RECEIVED:", data);

        const user = data.user;

        // update state
        connectedUsers.delete(user);

        // force UI refresh
        renderUsers(allUsers);

        // show popup
        showToast(`Disconnected from ${user}`, "success");
    });
});

