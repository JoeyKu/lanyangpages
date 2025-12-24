document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('login-form');
    const loginScreen = document.getElementById('login-screen');
    const dashboardScreen = document.getElementById('dashboard-screen');
    const loginError = document.getElementById('login-error');
    const logoutBtn = document.getElementById('logout-btn');
    const volunteerList = document.getElementById('volunteer-list');
    const refreshBtn = document.getElementById('refresh-btn');
    const loadingState = document.getElementById('loading-state');

    let currentVolunteers = [];
    let loggedInChapter = '';
    let authToken = localStorage.getItem('auth_token') || '';

    // Initialize: Check if already logged in
    if (authToken) {
        loggedInChapter = localStorage.getItem('logged_in_chapter') || '';
        document.getElementById('display-user').textContent = loggedInChapter;
        loginScreen.style.display = 'none';
        dashboardScreen.style.display = 'block';
        fetchVolunteers();
    } else {
        loginScreen.style.display = 'flex';
        dashboardScreen.style.display = 'none';
    }

    // Login logic
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const loginBtn = loginForm.querySelector('button[type="submit"]');
        const originalText = loginBtn.textContent;

        const user = document.getElementById('username').value;
        const pass = document.getElementById('password').value;

        // UI Loading state
        loginBtn.disabled = true;
        loginBtn.textContent = '登入中...';
        loginError.textContent = '';

        try {
            const response = await fetch('https://4ca729h0o8.execute-api.ap-northeast-1.amazonaws.com/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    chapter: user,
                    password: pass
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.message || '帳號或密碼錯誤');
            }

            const result = await response.json();
            console.log('Login Success:', result);

            // JWT Handling: Save token (checking multiple fallback keys)
            authToken = result.token || result.access_token || result.accessToken || result.idToken || '';
            loggedInChapter = user;

            if (authToken) {
                localStorage.setItem('auth_token', authToken);
                localStorage.setItem('logged_in_chapter', user);
                document.getElementById('display-user').textContent = user;
                loginScreen.style.display = 'none';
                dashboardScreen.style.display = 'block';
                fetchVolunteers();
            } else {
                console.error('No token found in response:', result);
                throw new Error('伺服器未回傳認證金鑰，請聯絡管理員');
            }
        } catch (error) {
            console.error('Login error:', error);
            loginError.textContent = error.message;
        } finally {
            loginBtn.disabled = false;
            loginBtn.textContent = originalText;
        }
    });

    // Logout logic
    logoutBtn.addEventListener('click', () => {
        // Clear local storage
        localStorage.removeItem('auth_token');
        localStorage.removeItem('logged_in_chapter');
        authToken = '';
        loggedInChapter = '';

        dashboardScreen.style.display = 'none';
        loginScreen.style.display = 'flex';
        volunteerList.innerHTML = '';
        loginForm.reset();
        loginError.textContent = '';
    });

    const addRecordBtn = document.getElementById('add-record-btn');
    const addModal = document.getElementById('add-modal');
    const closeModalBtn = document.getElementById('close-modal');
    const addRecordForm = document.getElementById('add-record-form');
    const addRowBtn = document.getElementById('add-row-btn');
    const volunteerRowsContainer = document.getElementById('volunteer-rows-container');

    // Modal control
    addRecordBtn.addEventListener('click', () => {
        addModal.classList.remove('hidden');
        resetModal();
    });

    closeModalBtn.addEventListener('click', () => {
        addModal.classList.add('hidden');
    });

    // Dynamic Row logic
    addRowBtn.addEventListener('click', () => {
        const firstRow = volunteerRowsContainer.querySelector('.volunteer-row-item');
        const newRow = firstRow.cloneNode(true);

        // Reset values
        newRow.querySelectorAll('input, select').forEach(el => el.value = '');

        // Show remove button
        const removeBtn = newRow.querySelector('.btn-remove-row');
        removeBtn.style.visibility = 'visible';
        removeBtn.addEventListener('click', () => {
            newRow.remove();
        });

        volunteerRowsContainer.appendChild(newRow);
    });

    function resetModal() {
        addRecordForm.reset();
        // Keep only first row and hide its remove button
        const rows = volunteerRowsContainer.querySelectorAll('.volunteer-row-item');
        rows.forEach((row, index) => {
            if (index === 0) {
                row.querySelector('.btn-remove-row').style.visibility = 'hidden';
            } else {
                row.remove();
            }
        });
    }

    // Add Record logic
    addRecordForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const submitBtn = addRecordForm.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn.textContent;

        // UI Loading state
        submitBtn.disabled = true;
        submitBtn.textContent = '傳送中...';

        const regName = document.getElementById('reg-name').value;
        const rowItems = volunteerRowsContainer.querySelectorAll('.volunteer-row-item');
        const currentYear = new Date().getFullYear();

        const payload = {
            creator: regName,
            records: []
        };

        rowItems.forEach(row => {
            const volName = row.querySelector('.vol-name').value;
            const volBranch = row.querySelector('.vol-branch').value;
            const volUnit = row.querySelector('.vol-unit').value;
            const volHours = parseFloat(row.querySelector('.vol-hours').value);
            const volRemarks = row.querySelector('.vol-remarks').value;

            payload.records.push({
                volunteer: volName,
                chapter: volBranch,
                unit: volUnit,
                hours: volHours,
                year: currentYear,
                remarks: volRemarks
            });
        });

        try {
            const response = await fetch('https://4ca729h0o8.execute-api.ap-northeast-1.amazonaws.com/hours', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authToken}`
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                // Handle non-2xx responses
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.message || `伺服器回應錯誤: ${response.status}`);
            }

            const result = await response.json();
            console.log('Success:', result);
            alert('紀錄新增成功！');

            // feedback and cleanup
            addModal.classList.add('hidden');
            fetchVolunteers(); // Refresh the list
        } catch (error) {
            console.error('Error details:', error);

            // Check if it's a TypeError (often caused by CORS or Network failure)
            if (error instanceof TypeError) {
                alert('新增失敗：連線錯誤或 CORS 阻擋。\n請確認 AWS API Gateway 已啟用 CORS 並允許您的網域。\n(Referrer Policy: strict-origin-when-cross-origin)');
            } else {
                alert('新增失敗：' + error.message);
            }
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = originalBtnText;
        }
    });

    // Data fetching logic (API Integration)
    async function fetchVolunteers() {
        loadingState.style.display = 'flex';
        volunteerList.innerHTML = '';

        try {
            const response = await fetch('https://4ca729h0o8.execute-api.ap-northeast-1.amazonaws.com/hours?limit=500', {
                headers: {
                    'Authorization': `Bearer ${authToken}`
                }
            });

            if (response.status === 401 || response.status === 403) {
                // Token expired or invalid
                logoutBtn.click();
                throw new Error('登入逾時，請重新登入');
            }

            if (!response.ok) throw new Error('無法取得資料');

            const data = await response.json();
            const items = data.items || [];

            // Group items by volunteer + chapter
            const groupedData = {};
            items.forEach(item => {
                const key = `${item.volunteer}-${item.chapter}`;
                if (!groupedData[key]) {
                    groupedData[key] = {
                        id: item.id, // Use the latest ID as reference
                        name: item.volunteer,
                        branch: item.chapter,
                        records: []
                    };
                }
                groupedData[key].records.push({
                    id: item.id,
                    registrar: item.creator || '系統',
                    hours: item.hours || 0,
                    unit: item.unit || '',
                    remarks: item.remarks || '',
                    date: item.created_at
                });
            });

            // Convert to array and sort by name
            currentVolunteers = Object.values(groupedData).sort((a, b) => a.name.localeCompare(b.name, 'zh-Hant'));

            renderTable(currentVolunteers);
        } catch (error) {
            console.error('Fetch error:', error);
            volunteerList.innerHTML = `<tr><td colspan="4" class="text-center text-danger">載入失敗：${error.message}</td></tr>`;
        } finally {
            loadingState.style.display = 'none';
        }
    }

    function renderTable(data) {
        volunteerList.innerHTML = data.map(v => {
            const totalHours = v.records.reduce((sum, r) => sum + r.hours, 0);
            // Get the most recent remark
            const latestRemark = v.records
                .filter(r => r.remarks)
                .sort((a, b) => new Date(b.date) - new Date(a.date))[0]?.remarks || '';

            return `
                <tr class="expandable-row" data-id="${v.id}">
                    <td><strong>${v.name}</strong></td>
                    <td>${v.branch}</td>
                    <td><span class="hours-badge">${totalHours} 小時</span></td>
                </tr>
                <tr id="detail-${v.id}" class="detail-row hidden">
                    <td colspan="3">
                        <div class="records-container">
                            <h4>服務紀錄</h4>
                            <div class="records-list">
                                ${v.records.map(r => `
                                    <div class="record-item">
                                        <div class="record-info">
                                            <span><span class="record-label">單位:</span><span class="record-value">${r.unit}</span></span>
                                            <span><span class="record-label">登記人:</span><span class="record-value">${r.registrar}</span></span>
                                            <span><span class="record-label">時數:</span><span class="record-value">${r.hours} 小時</span></span>
                                            ${r.remarks ? `<span><span class="record-label">備註:</span><span class="record-value">${r.remarks}</span></span>` : ''}
                                        </div>
                                        <button class="btn btn-danger delete-record-btn" 
                                                data-volunteer-id="${v.id}" 
                                                data-record-id="${r.id}">
                                            刪除
                                        </button>
                                    </div>
                                `).join('')}
                                ${v.records.length === 0 ? '<p class="text-muted">尚無紀錄</p>' : ''}
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        // Add Click listeners for expansion
        document.querySelectorAll('.expandable-row').forEach(row => {
            row.addEventListener('click', () => {
                const id = row.getAttribute('data-id');
                const detailRow = document.getElementById(`detail-${id}`);
                detailRow.classList.toggle('hidden');
            });
        });

        // Add Click listeners for delete buttons
        document.querySelectorAll('.delete-record-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent row toggle
                const volunteerId = btn.getAttribute('data-volunteer-id');
                const recordId = btn.getAttribute('data-record-id');
                deleteRecord(volunteerId, recordId);
            });
        });
    }

    async function deleteRecord(volunteerId, recordId) {
        const volunteer = currentVolunteers.find(v => v.id === volunteerId);
        if (!volunteer) return;

        const record = volunteer.records.find(r => r.id === recordId);
        if (!record) return;

        if (!confirm(`確定要刪除「${volunteer.name}」的這筆紀錄嗎？`)) return;

        try {
            const url = `https://4ca729h0o8.execute-api.ap-northeast-1.amazonaws.com/hours/${recordId}?volunteer=${encodeURIComponent(volunteer.name)}`;
            const response = await fetch(url, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${authToken}`
                }
            });

            if (!response.ok) throw new Error('刪除失敗');

            alert('紀錄已成功刪除');
            fetchVolunteers(); // Refresh list to reflect changes
        } catch (error) {
            console.error('Delete error:', error);
            alert('刪除失敗：' + error.message);
        }
    }

    refreshBtn.addEventListener('click', fetchVolunteers);
});
