document.addEventListener("DOMContentLoaded", () => {

    let currentIndex = 0;
    const LIMIT = 5;

    // 🔹 Helper to safely set text
    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.innerText = value;
    };

    // 🔥 Load profile data
    function loadProfile() {
        fetch("/profile-data", {
            credentials: "include"
        })
            .then(res => {
                if (res.status === 401) {
                    window.location.href = "/login";
                    return;
                }
                if (!res.ok) {
                    throw new Error("Failed to load profile");
                }
                return res.json();
            })
            .then(data => {
                if (!data) return;

                setText("username", data.username);
                setText("email", data.email);
                setText("sent", data.sent);
                setText("received", data.received);
                setText("lastActive", data.lastActive);
            })
            .catch(err => {
                console.error("Profile fetch error:", err);
            });
    }

    // 🔥 Load recent transfers
    function loadTransfers(reset = false) {
        fetch(`/recent-transfers?start=${currentIndex}&limit=${LIMIT}`, {
            credentials: "include"
        })
            .then(res => {
                if (res.status === 401) {
                    window.location.href = "/login";
                    return;
                }
                if (!res.ok) {
                    throw new Error("Failed to load transfers");
                }
                return res.json();
            })
            .then(data => {
                if (!data) return;

                const list = document.getElementById("transferList");
                if (!list) return;

                // ✅ only clear when resetting
                if (reset) {
                    list.innerHTML = "";
                    currentIndex = 0;
                    const btn = document.getElementById("loadMoreBtn");
                    if (btn) {
                        btn.innerText = "Load More";
                        btn.disabled = false;
                    }
                }

                if (data.length === 0 && currentIndex === 0) {
                    list.innerHTML =
                        "<li class='list-group-item activity-item'>No transfers yet</li>";
                    return;
                }

                data.forEach(t => {
                    const li = document.createElement("li");
                    li.className = "list-group-item activity-item";
                    li.innerText = `${t.sender} → ${t.receiver} (${t.filename})`;
                    list.appendChild(li);
                });

                // ✅ move pointer forward
                currentIndex += data.length;

                // ✅ disable button if no more data
                if (data.length < LIMIT) {
                    const btn = document.getElementById("loadMoreBtn");
                    if (btn) {
                        btn.innerText = "No More";
                        btn.disabled = true;
                    }
                }
            })
            .catch(err => {
                console.error("Transfers error:", err);

                const list = document.getElementById("transferList");
                if (list) {
                    list.innerHTML =
                        "<li class='list-group-item activity-item text-danger'>Error loading transfers</li>";
                }
            });
    }

    // 🔥 INITIAL LOAD
    loadProfile();
    loadTransfers(true);

    document.getElementById("loadMoreBtn")?.addEventListener("click", () => {
        loadTransfers();
    });

    // 🔥 AUTO REFRESH (with cleanup)
    const profileInterval = setInterval(loadProfile, 5000);
    //const transferInterval = setInterval(loadTransfers, 5000);

    window.addEventListener("beforeunload", () => {
        clearInterval(profileInterval);
        //clearInterval(transferInterval);
    });

});


function updateProfile() {

    const newUsername = document.getElementById("newUsername").value.trim();
    const currentPassword = document.getElementById("currentPassword").value;
    const newPassword = document.getElementById("newPassword").value;

    if (!newUsername && !newPassword) {
        alert("Nothing to update");
        return;
    }

    fetch("/update-profile", {
        method: "POST",
        credentials: "include",   // 🔥 FIX 1
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            username: newUsername,
            currentPassword: currentPassword,
            newPassword: newPassword
        })
    })
        .then(async res => {

            const data = await res.json();  // 🔥 FIX 2

            if (!res.ok) {
                throw new Error(data.error || "Update failed");
            }

            return data;
        })
        .then(data => {
            alert("Profile updated successfully!");
            location.reload();
        })
        .catch(err => {
            console.error("Update error:", err);
            alert(err.message);  // 🔥 shows real backend error
        });
}