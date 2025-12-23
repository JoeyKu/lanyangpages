document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('login-form');
    const loginScreen = document.getElementById('login-screen');
    const dashboardScreen = document.getElementById('dashboard-screen');
    const loginError = document.getElementById('login-error');
    const logoutBtn = document.getElementById('logout-btn');
    const volunteerList = document.getElementById('volunteer-list');
    const refreshBtn = document.getElementById('refresh-btn');
    const loadingState = document.getElementById('loading-state');

    // Mock Database
    const mockVolunteers = [
        {
            id: 1,
            name: '王小明',
            branch: '宜一',
            records: [
                { id: 101, registrar: '知林法師', hours: 20, unit: '服務台 101' },
                { id: 102, registrar: '知林法師', hours: 25, unit: '流通處' }
            ]
        },
        {
            id: 2,
            name: '李美華',
            branch: '宜一',
            records: [
                { id: 201, registrar: '明恆法師', hours: 120, unit: '書車義工' }
            ]
        },
        {
            id: 3,
            name: '張建國',
            branch: '蘭二',
            records: [
                { id: 301, registrar: '知林法師', hours: 88, unit: '園藝組' }
            ]
        },
        {
            id: 4,
            name: '林宜君',
            branch: '宜三',
            records: [
                { id: 401, registrar: '知林法師', hours: 32, unit: '茶席' }
            ]
        },
        {
            id: 5,
            name: '陳致中',
            branch: '宜四',
            records: [
                { id: 501, registrar: '知林法師', hours: 210, unit: '金剛巡寮' }
            ]
        },
        {
            id: 6,
            name: '黃詩涵',
            branch: '宜五',
            records: [
                { id: 601, registrar: '知修法師', hours: 56, unit: '典座' }
            ]
        }
    ];

    // Login logic
    loginForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const user = document.getElementById('username').value;
        const pass = document.getElementById('password').value;

        // Simple mock auth
        if (user === 'admin' && pass === '1234') {
            loginScreen.style.display = 'none';
            dashboardScreen.style.display = 'block';
            fetchVolunteers();
        } else {
            loginError.textContent = '帳號或密碼錯誤 (admin / 1234)';
        }
    });

    // Logout logic
    logoutBtn.addEventListener('click', () => {
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
    addRecordForm.addEventListener('submit', (e) => {
        e.preventDefault();

        const regName = document.getElementById('reg-name').value;
        const rowItems = volunteerRowsContainer.querySelectorAll('.volunteer-row-item');

        rowItems.forEach(row => {
            const volName = row.querySelector('.vol-name').value;
            const volBranch = row.querySelector('.vol-branch').value;
            const volUnit = row.querySelector('.vol-unit').value;
            const volHours = parseFloat(row.querySelector('.vol-hours').value);

            // Find existing volunteer
            let volunteer = mockVolunteers.find(v => v.name === volName && v.branch === volBranch);

            const newRecord = {
                id: Date.now() + Math.random(), // Add random to ensure uniqueness in same batch
                registrar: regName,
                hours: volHours,
                unit: volUnit
            };

            if (volunteer) {
                volunteer.records.push(newRecord);
            } else {
                const newVolunteer = {
                    id: mockVolunteers.length + 1,
                    name: volName,
                    branch: volBranch,
                    records: [newRecord]
                };
                mockVolunteers.push(newVolunteer);
            }
        });

        // feedback and cleanup
        addModal.classList.add('hidden');
        renderTable(mockVolunteers);
    });

    // Data fetching logic (Simulated API)
    async function fetchVolunteers() {
        loadingState.style.display = 'flex';
        volunteerList.innerHTML = '';

        // Simulate network delay
        await new Promise(resolve => setTimeout(resolve, 800));

        renderTable(mockVolunteers);
        loadingState.style.display = 'none';
    }

    function renderTable(data) {
        volunteerList.innerHTML = data.map(v => {
            const totalHours = v.records.reduce((sum, r) => sum + r.hours, 0);
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
                const volunteerId = parseInt(btn.getAttribute('data-volunteer-id'));
                const recordId = parseInt(btn.getAttribute('data-record-id'));
                deleteRecord(volunteerId, recordId);
            });
        });
    }

    function deleteRecord(volunteerId, recordId) {
        const volunteer = mockVolunteers.find(v => v.id === volunteerId);
        if (volunteer) {
            volunteer.records = volunteer.records.filter(r => r.id !== recordId);
            renderTable(mockVolunteers);
            // Re-expand the row we were looking at
            const detailRow = document.getElementById(`detail-${volunteerId}`);
            if (detailRow) detailRow.classList.remove('hidden');
        }
    }

    refreshBtn.addEventListener('click', fetchVolunteers);
});
