/*
  CareBlink - Dashboard Javascript Controller
  Manages: Tab navigation, webcam stream control, live API polling,
           Web Audio API sirens, biometric charts (Chart.js), data exports (SheetJS/jsPDF).
*/

document.addEventListener('DOMContentLoaded', () => {
    // Session State Object
    const appState = {
        activeTab: 'live-dashboard',
        activeAlert: null,
        soundEnabled: true,
        pollingInterval: null,
        audioContext: null,
        localLastBlinkTime: 0.0,
        cameraRunning: false,
        telemetryChart: null,
        earHistory: Array(30).fill(0.28),
        chartLabels: Array(30).fill(''),
        sirenOscillator: null,
        sirenLfo: null,
        sirenGain: null,
        systemLogs: [
            "[CareBlink Initializing] Checked database connections.",
            "[Database Service] Connection active.",
            "[Webcam Controller] Waiting for operator trigger..."
        ]
    };

    // DOM Caches
    const tabMenuItems = document.querySelectorAll('.menu-item');
    const contentPanels = document.querySelectorAll('.content-panel');
    const tabTitle = document.getElementById('tab-title');
    const tabSubtitle = document.getElementById('tab-subtitle');
    const soundToggleBtn = document.getElementById('sound-toggle-btn');
    const virtualBulb = document.getElementById('virtual-bulb');
    const bulbStatusText = document.getElementById('bulb-status-text');
    const normalStateView = document.getElementById('normal-state-view');
    const emergencyStateView = document.getElementById('emergency-state-view');
    const dismissAlertBtn = document.getElementById('dismiss-alert-btn');
    const refreshHistoryBtn = document.getElementById('refresh-history-btn');
    const registerPatientForm = document.getElementById('register-patient-form');
    const patientsTableBody = document.querySelector('#patients-table tbody');
    const historyTableBody = document.querySelector('#history-table tbody');
    
    const dbCameraStartBtn = document.getElementById('dashboard-camera-start');
    const dbCameraStopBtn = document.getElementById('dashboard-camera-stop');
    const dbCameraStatusBadge = document.getElementById('dashboard-camera-status');
    const sidebarDbDialect = document.getElementById('sidebar-db-dialect');
    
    // Page Descriptions
    const tabDetails = {
        'live-dashboard': { title: 'Live Monitor Dashboard', subtitle: 'Real-time patient monitoring feed and status alerts.' },
        'patient-records': { title: 'Patients Registry', subtitle: 'Manage and register patient profiles for blink monitoring.' },
        'alert-history': { title: 'Emergency Incident Logs', subtitle: 'Historical archive of eye-blink emergency dispatches.' },
        'hospital-records': { title: 'All Hospital Records', subtitle: 'Isolated medical registries and monitoring archives segmented by facility.' },
        'doctor-dashboard': { title: 'Doctor Console', subtitle: 'Active shift configurations and computer vision triggers.' },
        'patient-dashboard': { title: 'Patient Bio-Telemetry', subtitle: 'Dynamic EAR indices, eye coordinates, and gaze charts.' },
        'emergency-siren-dashboard': { title: 'Emergency Alarm HUD', subtitle: 'High-visibility ward monitor mapping active sirens.' },
        'admin-dashboard': { title: 'Admin Management Console', subtitle: 'Environment logging and system configuration dial.' }
    };

    // ==========================================
    // Sidebar Tabs Controller
    // ==========================================
    tabMenuItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const target = item.getAttribute('data-tab');
            if (!target) return;

            tabMenuItems.forEach(mi => mi.classList.remove('active'));
            item.classList.add('active');

            contentPanels.forEach(panel => panel.classList.remove('active'));
            const matchedPanel = document.getElementById(`${target}-tab`);
            if (matchedPanel) matchedPanel.classList.add('active');

            if (tabTitle) tabTitle.textContent = tabDetails[target].title;
            if (tabSubtitle) tabSubtitle.textContent = tabDetails[target].subtitle;
            
            appState.activeTab = target;
            addTerminalLog(`[Navigation] Shifter page view context to: ${tabDetails[target].title}`);

            // Lazy loaders
            if (target === 'patient-records') {
                loadPatientsList();
            } else if (target === 'alert-history') {
                loadAlertHistory();
            } else if (target === 'hospital-records') {
                loadHospitalRecords();
            } else if (target === 'patient-dashboard') {
                initTelemetryChart();
            } else if (target === 'admin-dashboard') {
                loadAdminConsole();
            }
        });
    });

    // ==========================================
    // Camera streaming API Handlers
    // ==========================================
    async function updateCameraTelemetry() {
        try {
            const response = await fetch('/api/camera/status');
            const data = await response.json();
            appState.cameraRunning = data.is_running;
            
            const cameraImg = document.getElementById('camera-stream-img');
            const cameraPlaceholder = document.getElementById('camera-placeholder-box');
            
            if (appState.cameraRunning) {
                if (dbCameraStatusBadge) {
                    dbCameraStatusBadge.className = 'badge bg-success-soft text-success px-2 py-1 rounded-2';
                    dbCameraStatusBadge.textContent = 'ONLINE';
                }
                if (dbCameraStartBtn) dbCameraStartBtn.disabled = true;
                if (dbCameraStopBtn) dbCameraStopBtn.disabled = false;
                
                const statusBadgeEl = document.getElementById('system-status-badge');
                if (statusBadgeEl) {
                    statusBadgeEl.querySelector('.status-text').textContent = 'Camera Online';
                    statusBadgeEl.querySelector('.pulse-dot').className = 'pulse-dot green';
                    statusBadgeEl.className = 'status-badge bg-success-soft text-success px-3 py-2 rounded-3 d-flex align-items-center gap-2';
                }
                
                if (cameraImg && cameraPlaceholder) {
                    cameraImg.src = '/video_feed';
                    cameraImg.classList.remove('d-none');
                    cameraPlaceholder.classList.add('d-none');
                }

                // Update text boxes
                document.getElementById('tele-patient-name').textContent = data.patient_name;
                document.getElementById('tele-patient-id').textContent = data.patient_id;
                document.getElementById('tele-patient-room').textContent = `Room ${data.room_number}`;
                document.getElementById('tele-ear-base').textContent = Number(data.baseline_ear).toFixed(3);
                document.getElementById('tele-ear-current').textContent = Number(data.current_ear).toFixed(3);
                document.getElementById('tele-ear-thresh').textContent = Number(data.ear_threshold).toFixed(3);
                document.getElementById('tele-pupil-dist').textContent = Number(data.pupil_distance).toFixed(1) + ' mm';
                document.getElementById('tele-gaze-pos').textContent = data.current_gaze.toUpperCase();
                document.getElementById('tele-blinks-count').textContent = data.current_blinks;
                
                // Shift Gaze Highlight Color
                const gazeText = document.getElementById('tele-gaze-pos');
                if (gazeText) {
                    if (data.current_gaze === 'left' || data.current_gaze === 'right') {
                        gazeText.className = 'text-danger font-mono d-block';
                    } else {
                        gazeText.className = 'text-accent font-mono d-block';
                    }
                }

                // Decoded thoughts banner
                let thoughtMsg = data.mind_thoughts || "Calm and resting.";
                if (data.current_blinks > 0) {
                    const dict = {
                        1: '⚡ Thought: "Yes / I hear you."',
                        2: '⚡ Thought: "No / Disagree."',
                        3: '⚡ Thought: "Requesting water."',
                        4: '⚡ Thought: "I feel cold."',
                        5: '🚨 Thought: "EMERGENCY ALERT!"'
                    };
                    thoughtMsg = dict[Math.min(data.current_blinks, 5)];
                }
                document.getElementById('tele-mind-thoughts').textContent = thoughtMsg;

                // Push dynamic charts updates
                if (appState.telemetryChart) {
                    appState.earHistory.shift();
                    appState.earHistory.push(data.current_ear);
                    appState.telemetryChart.update('none');
                }
                
                const pdStat = document.getElementById('patient-pd-stat');
                if (pdStat) pdStat.textContent = Number(data.current_pd).toFixed(1) + ' mm';
                
            } else {
                if (dbCameraStatusBadge) {
                    dbCameraStatusBadge.className = 'badge bg-danger-soft text-danger px-2 py-1 rounded-2';
                    dbCameraStatusBadge.textContent = 'OFFLINE';
                }
                if (dbCameraStartBtn) dbCameraStartBtn.disabled = false;
                if (dbCameraStopBtn) dbCameraStopBtn.disabled = true;
                
                const statusBadgeEl = document.getElementById('system-status-badge');
                if (statusBadgeEl) {
                    statusBadgeEl.querySelector('.status-text').textContent = 'Camera Offline';
                    statusBadgeEl.querySelector('.pulse-dot').className = 'pulse-dot red';
                    statusBadgeEl.className = 'status-badge bg-danger-soft text-danger px-3 py-2 rounded-3 d-flex align-items-center gap-2';
                }
                
                if (cameraImg && cameraPlaceholder) {
                    cameraImg.removeAttribute('src');
                    cameraImg.classList.add('d-none');
                    cameraPlaceholder.classList.remove('d-none');
                }
            }
        } catch (err) {
            console.error('Status fetch warning:', err);
        }
    }

    dbCameraStartBtn.addEventListener('click', async () => {
        try {
            dbCameraStartBtn.disabled = true;
            const selectId = document.getElementById('monitor-patient-select')?.value || 'PT-2045';
            addTerminalLog(`[Camera] Requesting stream start for: ${selectId}`);
            const response = await fetch('/api/camera/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ patient_id: selectId })
            });
            const data = await response.json();
            if (data.success) {
                showToast("Webcam Monitoring Activated!", "success");
                addTerminalLog("[Camera] Stream initialized successfully.");
                updateCameraTelemetry();
            }
        } catch (err) {
            dbCameraStartBtn.disabled = false;
            showToast("Webcam start command failed.", "danger");
        }
    });

    dbCameraStopBtn.addEventListener('click', async () => {
        try {
            dbCameraStopBtn.disabled = true;
            addTerminalLog("[Camera] Requesting stream shutdown.");
            const response = await fetch('/api/camera/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();
            if (data.success) {
                showToast("Webcam Monitoring Deactivated.", "info");
                addTerminalLog("[Camera] Stream disconnected.");
                updateCameraTelemetry();
            }
        } catch (err) {
            dbCameraStopBtn.disabled = false;
        }
    });

    // ==========================================
    // Active Alarm Polling & Sirens (Web Audio)
    // ==========================================
    async function checkActiveAlerts() {
        try {
            const response = await fetch('/api/alerts/active');
            const data = await response.json();
            
            if (sidebarDbDialect && data.db_dialect) {
                sidebarDbDialect.textContent = data.db_dialect;
            }

            // Play beep on normal blinks
            if (data.last_blink_time && data.last_blink_time > appState.localLastBlinkTime) {
                if (appState.localLastBlinkTime > 0.0) {
                    playSoftBeep();
                }
                appState.localLastBlinkTime = data.last_blink_time;
            }

            if (data.has_active) {
                appState.activeAlert = data.alert;
                renderActiveIncident(data.alert);
            } else {
                appState.activeAlert = null;
                renderSafeState();
            }
            
            // Polling camera metrics updates
            updateCameraTelemetry();
        } catch (err) {
            console.error('Blink Polling error:', err);
        }
    }

    function renderActiveIncident(alert) {
        if (normalStateView) normalStateView.classList.add('d-none');
        if (emergencyStateView) emergencyStateView.classList.remove('d-none');
        
        if (virtualBulb) {
            virtualBulb.className = 'virtual-bulb status-emergency';
        }
        if (bulbStatusText) {
            bulbStatusText.textContent = 'PATIENT EMERGENCY';
            bulbStatusText.className = 'h6 text-white font-mono mb-2 text-danger';
        }

        // Fill data boxes
        document.getElementById('emg-patient-name').textContent = alert.name;
        document.getElementById('emg-patient-room').textContent = `${alert.patient_id} / ${alert.room_number}`;
        document.getElementById('emg-message').textContent = alert.message;
        document.getElementById('emg-mind-thoughts').textContent = alert.mind_thoughts || "Urgent assistance requested!";
        document.getElementById('emergency-time').textContent = `Triggered: ${alert.created_at}`;

        // Update High Visibility HUD
        const hudCard = document.getElementById('hud-patient-card');
        const hudTitle = document.getElementById('hud-status-title');
        const hudDesc = document.getElementById('hud-status-desc');
        const hudContainer = hudTitle.parentElement;
        
        if (hudTitle && hudCard) {
            hudTitle.textContent = "EMERGENCY SIREN ACTIVE";
            hudTitle.className = "text-danger display-4 fw-bold mb-3 tracking-wide animate-pulse";
            if (hudDesc) hudDesc.classList.add('d-none');
            hudCard.classList.remove('d-none');
            
            document.getElementById('hud-patient-name').textContent = alert.name;
            document.getElementById('hud-patient-room').textContent = alert.room_number;
            document.getElementById('hud-patient-msg').textContent = alert.message;
            document.getElementById('hud-patient-mind').textContent = alert.mind_thoughts || "Emergency code triggered";
            
            if (hudContainer) hudContainer.classList.add('alarm-active');
        }

        // Trigger wailing alarm siren sound
        startEmergencySiren();
    }

    function renderSafeState() {
        if (emergencyStateView) emergencyStateView.classList.add('d-none');
        if (normalStateView) normalStateView.classList.remove('d-none');

        if (virtualBulb) {
            virtualBulb.className = appState.cameraRunning ? 'virtual-bulb status-safe' : 'virtual-bulb status-warning';
        }
        if (bulbStatusText) {
            bulbStatusText.textContent = appState.cameraRunning ? 'SYSTEM SECURE' : 'CAMERA OFFLINE';
            bulbStatusText.className = appState.cameraRunning ? 'h6 text-white font-mono mb-2 text-success' : 'h6 text-white font-mono mb-2 text-warning';
        }

        // Reset HUD View
        const hudCard = document.getElementById('hud-patient-card');
        const hudTitle = document.getElementById('hud-status-title');
        const hudDesc = document.getElementById('hud-status-desc');
        const hudContainer = hudTitle?.parentElement;

        if (hudTitle && hudCard) {
            hudTitle.textContent = "SYSTEM SECURE";
            hudTitle.className = "text-white display-4 fw-bold mb-3 tracking-wide";
            if (hudDesc) hudDesc.classList.remove('d-none');
            hudCard.classList.add('d-none');
            
            if (hudContainer) hudContainer.classList.remove('alarm-active');
        }

        // Stop siren alarm sound
        stopEmergencySiren();
    }

    dismissAlertBtn?.addEventListener('click', dismissActiveAlert);
    document.getElementById('hud-dismiss-btn')?.addEventListener('click', dismissActiveAlert);

    async function dismissActiveAlert() {
        try {
            stopEmergencySiren();
            renderSafeState();
            addTerminalLog("[Alert Reset] Operator dismissed active threat coordinates.");
            
            await fetch('/api/alerts/dismiss', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            showToast("Emergency siren resolved.", "success");
        } catch (err) {
            console.error('Dismiss API error:', err);
        }
    }

    // ==========================================
    // Web Audio Synthesizer Logic
    // ==========================================
    function initAudio() {
        if (!appState.audioContext) {
            appState.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
    }

    function playSoftBeep() {
        if (!appState.soundEnabled) return;
        try {
            initAudio();
            const ctx = appState.audioContext;
            if (ctx.state === 'suspended') ctx.resume();
            
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            
            osc.connect(gain);
            gain.connect(ctx.destination);
            
            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            
            gain.gain.setValueAtTime(0.12, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
            
            osc.start();
            osc.stop(ctx.currentTime + 0.12);
        } catch (e) {
            console.error(e);
        }
    }

    function startEmergencySiren() {
        if (appState.sirenOscillator) return;
        if (!appState.soundEnabled) return;
        try {
            initAudio();
            const ctx = appState.audioContext;
            if (ctx.state === 'suspended') ctx.resume();
            
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            
            osc.connect(gain);
            gain.connect(ctx.destination);
            
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(750, ctx.currentTime);
            
            // Siren pitch sweep LFO
            const lfo = ctx.createOscillator();
            const lfoGain = ctx.createGain();
            lfo.type = 'triangle';
            lfo.frequency.setValueAtTime(2.0, ctx.currentTime); // 2Hz frequency
            lfoGain.gain.setValueAtTime(180, ctx.currentTime);
            
            lfo.connect(lfoGain);
            lfoGain.connect(osc.frequency);
            
            gain.gain.setValueAtTime(0.01, ctx.currentTime);
            gain.gain.linearRampToValueAtTime(0.3, ctx.currentTime + 0.1);
            
            lfo.start();
            osc.start();
            
            appState.sirenOscillator = osc;
            appState.sirenLfo = lfo;
            appState.sirenGain = gain;
        } catch (e) {
            console.error('Audio start error:', e);
        }
    }

    function stopEmergencySiren() {
        if (appState.sirenOscillator) {
            try {
                const ctx = appState.audioContext;
                const osc = appState.sirenOscillator;
                const lfo = appState.sirenLfo;
                const gain = appState.sirenGain;
                
                gain.gain.setValueAtTime(gain.gain.value, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1);
                
                osc.stop(ctx.currentTime + 0.15);
                lfo.stop(ctx.currentTime + 0.15);
            } catch (e) {
                console.error(e);
            }
            appState.sirenOscillator = null;
            appState.sirenLfo = null;
            appState.sirenGain = null;
        }
    }

    soundToggleBtn.addEventListener('click', () => {
        appState.soundEnabled = !appState.soundEnabled;
        const icon = soundToggleBtn.querySelector('i');
        const text = soundToggleBtn.querySelector('span');
        
        if (appState.soundEnabled) {
            icon.className = 'fa-solid fa-volume-high';
            text.textContent = 'Sound: Enabled';
        } else {
            icon.className = 'fa-solid fa-volume-xmark';
            text.textContent = 'Sound: Muted';
            stopEmergencySiren();
        }
    });

    document.getElementById('hud-mute-btn')?.addEventListener('click', () => {
        soundToggleBtn.click();
        const hudMute = document.getElementById('hud-mute-btn');
        if (hudMute) {
            if (appState.soundEnabled) {
                hudMute.className = 'fa-solid fa-bell text-white cursor-pointer';
            } else {
                hudMute.className = 'fa-solid fa-bell-slash text-white cursor-pointer';
            }
        }
    });

    // ==========================================
    // Form registry submission
    // ==========================================
    registerPatientForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const payload = {
            patient_id: document.getElementById('reg-patient-id').value.trim(),
            name: document.getElementById('reg-name').value.trim(),
            age: parseInt(document.getElementById('reg-age').value),
            room_number: document.getElementById('reg-room').value.trim(),
            medical_condition: document.getElementById('reg-condition').value.trim(),
            ear_threshold: parseFloat(document.getElementById('cal-ear-threshold')?.value || 0.22),
            baseline_ear: parseFloat(document.getElementById('cal-baseline-ear')?.value || 0.28),
            pupil_distance: parseFloat(document.getElementById('cal-pupil-distance')?.value || 60.0),
            mind_thoughts: document.getElementById('reg-mind-thoughts')?.value.trim() || 'Calm and resting.'
        };

        try {
            const response = await fetch('/api/patients', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            
            if (data.success) {
                showToast("Patient Registered Successfully!", "success");
                registerPatientForm.reset();
                
                const preview = document.getElementById('calibration-results-preview');
                if (preview) preview.classList.add('d-none');
                
                loadPatientsList();
                loadPatientSelect();
            } else {
                showToast(`Error: ${data.message}`, "danger");
            }
        } catch (err) {
            showToast("Failed to connect to web server.", "danger");
        }
    });

    // Load Patient lists
    async function loadPatientsList() {
        if (!patientsTableBody) return;
        try {
            patientsTableBody.innerHTML = '<tr><td colspan="5" class="py-4 text-center text-secondary"><i class="fa-solid fa-spinner fa-spin me-1"></i> Querying records...</td></tr>';
            
            const response = await fetch('/api/patients');
            const list = await response.json();
            
            if (list.length === 0) {
                patientsTableBody.innerHTML = '<tr><td colspan="5" class="py-4 text-center text-secondary">No patients registered.</td></tr>';
                return;
            }

            patientsTableBody.innerHTML = '';
            list.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="px-4 py-3"><strong>${escapeHTML(p.patient_id)}</strong></td>
                    <td class="px-4 py-3">${escapeHTML(p.name)}</td>
                    <td class="px-4 py-3">${escapeHTML(String(p.age))}</td>
                    <td class="px-4 py-3"><span class="badge bg-dark-soft text-white px-2 py-1">${escapeHTML(p.room_number)}</span></td>
                    <td class="px-4 py-3 text-secondary">${escapeHTML(p.medical_condition)}</td>
                `;
                patientsTableBody.appendChild(tr);
            });
        } catch (err) {
            patientsTableBody.innerHTML = '<tr><td colspan="5" class="py-4 text-center text-danger">Registry connection failed.</td></tr>';
        }
    }

    async function loadPatientSelect() {
        const select = document.getElementById('monitor-patient-select');
        if (!select) return;
        try {
            const response = await fetch('/api/patients');
            const list = await response.json();
            select.innerHTML = '';
            list.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.patient_id;
                opt.textContent = `${p.name} (${p.room_number})`;
                select.appendChild(opt);
            });
        } catch (err) {
            console.error(err);
        }
    }

    // ==========================================
    // Incident Logs / Alert history lists
    // ==========================================
    refreshHistoryBtn?.addEventListener('click', loadAlertHistory);

    async function loadAlertHistory() {
        if (!historyTableBody) return;
        try {
            historyTableBody.innerHTML = '<tr><td colspan="7" class="py-4 text-center text-secondary"><i class="fa-solid fa-spinner fa-spin me-1"></i> Querying incidents...</td></tr>';
            
            const response = await fetch('/api/alerts/history');
            const data = await response.json();
            
            if (data.length === 0) {
                historyTableBody.innerHTML = '<tr><td colspan="7" class="py-4 text-center text-secondary">No incident logs archived.</td></tr>';
                return;
            }

            historyTableBody.innerHTML = '';
            data.forEach(log => {
                const badge = log.status === 'active' 
                    ? '<span class="text-danger fw-bold"><i class="fa-solid fa-bell animate-pulse me-1"></i>Active</span>'
                    : '<span class="text-success"><i class="fa-solid fa-circle-check me-1"></i>Resolved</span>';
                
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="px-4 py-3 font-mono text-secondary small">${escapeHTML(log.created_at)}</td>
                    <td class="px-4 py-3"><strong>${escapeHTML(log.patient_id)}</strong></td>
                    <td class="px-4 py-3">${escapeHTML(log.name)}</td>
                    <td class="px-4 py-3"><span class="badge bg-dark-soft text-white px-2 py-1">${escapeHTML(log.room_number)}</span></td>
                    <td class="px-4 py-3 text-secondary small">${escapeHTML(log.message)}</td>
                    <td class="px-4 py-3">${badge}</td>
                    <td class="px-4 py-3 font-mono text-secondary small">${escapeHTML(log.resolved_at)}</td>
                `;
                historyTableBody.appendChild(tr);
            });
        } catch (err) {
            historyTableBody.innerHTML = '<tr><td colspan="7" class="py-4 text-center text-danger">Failed to retrieve logs database.</td></tr>';
        }
    }

    // ==========================================
    // Hospital records & video clips loaders
    // ==========================================
    async function loadHospitalRecords() {
        const hospName = document.getElementById('hosp-profile-name');
        const hospState = document.getElementById('hosp-profile-state');
        const hospPatientsCount = document.getElementById('hosp-profile-patients-count');
        const hospAlertsCount = document.getElementById('hosp-profile-alerts-count');
        const hospPatientsTableBody = document.querySelector('#hosp-patients-table tbody');
        const hospVideosTableBody = document.querySelector('#hosp-videos-table tbody');
        
        try {
            if (hospPatientsTableBody) hospPatientsTableBody.innerHTML = '<tr><td colspan="4" class="py-3 text-center text-secondary"><i class="fa-solid fa-spinner fa-spin"></i></td></tr>';
            if (hospVideosTableBody) hospVideosTableBody.innerHTML = '<tr><td colspan="5" class="py-3 text-center text-secondary"><i class="fa-solid fa-spinner fa-spin"></i></td></tr>';
            
            const response = await fetch('/api/hospital/records');
            const data = await response.json();
            
            if (hospName) hospName.textContent = data.hospital_name;
            if (hospState) hospState.textContent = data.state;
            if (hospPatientsCount) hospPatientsCount.textContent = `${data.patients.length} Patients`;
            if (hospAlertsCount) hospAlertsCount.textContent = `${data.alerts.length} Incidents`;
            
            if (hospPatientsTableBody) {
                if (data.patients.length === 0) {
                    hospPatientsTableBody.innerHTML = '<tr><td colspan="4" class="py-3 text-center text-secondary">No patients registered.</td></tr>';
                } else {
                    hospPatientsTableBody.innerHTML = '';
                    data.patients.forEach(p => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td class="px-4 py-3"><strong>${escapeHTML(p.patient_id)}</strong></td>
                            <td class="px-4 py-3">${escapeHTML(p.name)}</td>
                            <td class="px-4 py-3"><span class="badge bg-dark-soft text-white px-2 py-1">${escapeHTML(p.room_number)}</span></td>
                            <td class="px-4 py-3 text-secondary small">${escapeHTML(p.medical_condition)}</td>
                        `;
                        hospPatientsTableBody.appendChild(tr);
                    });
                }
            }

            if (hospVideosTableBody) {
                if (data.alerts.length === 0) {
                    hospVideosTableBody.innerHTML = '<tr><td colspan="5" class="py-3 text-center text-secondary">No video telemetry clips saved.</td></tr>';
                } else {
                    hospVideosTableBody.innerHTML = '';
                    data.alerts.forEach(a => {
                        const videoLink = a.video_filename 
                            ? `<a href="/all_records/${escapeHTML(a.video_filename)}" target="_blank" class="btn btn-dark-soft btn-sm text-accent"><i class="fa-solid fa-circle-play text-danger me-1"></i> Watch Video</a>`
                            : `<span class="text-secondary small"><i class="fa-solid fa-video-slash me-1"></i> No Clip</span>`;
                        
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td class="px-4 py-3 font-mono text-secondary small">${escapeHTML(a.created_at)}</td>
                            <td class="px-4 py-3"><strong>${escapeHTML(a.patient_id)}</strong></td>
                            <td class="px-4 py-3">${escapeHTML(a.name)}</td>
                            <td class="px-4 py-3 text-secondary small">${escapeHTML(a.message)}</td>
                            <td class="px-4 py-3">${videoLink}</td>
                        `;
                        hospVideosTableBody.appendChild(tr);
                    });
                }
            }
        } catch (err) {
            console.error('Records fetch error:', err);
        }
    }

    // ==========================================
    // Biometric Telemetry Chart (Chart.js)
    // ==========================================
    function initTelemetryChart() {
        const canvas = document.getElementById('patient-telemetry-chart');
        if (!canvas) return;
        if (appState.telemetryChart) return; // already loaded
        
        const ctx = canvas.getContext('2d');
        appState.telemetryChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: appState.chartLabels,
                datasets: [{
                    label: 'Eye Aspect Ratio (EAR)',
                    data: appState.earHistory,
                    borderColor: '#06b6d4',
                    borderWidth: 2,
                    fill: true,
                    backgroundColor: 'rgba(6, 182, 212, 0.08)',
                    tension: 0.35,
                    pointRadius: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: { display: false },
                    y: {
                        min: 0.0,
                        max: 0.45,
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#94a3b8' }
                    }
                }
            }
        });
    }

    // ==========================================
    // Calibration Modal controller
    // ==========================================
    const btnScan = document.getElementById('btn-scan-patient');
    const scanModal = document.getElementById('eye-scan-modal');
    const btnCancelScan = document.getElementById('btn-cancel-scan');
    const btnApplyScan = document.getElementById('btn-apply-scan');
    const scanImg = document.getElementById('scan-stream-img');
    const scanProgress = document.getElementById('scan-progress-bar');
    const scanStatus = document.getElementById('scan-status-text');
    const scanActiveView = document.getElementById('scan-active-view');
    const scanResultView = document.getElementById('scan-result-view');
    
    let calibrationController = null;
    let cachedCalibrationData = null;

    btnScan?.addEventListener('click', async () => {
        scanActiveView.classList.remove('d-none');
        scanResultView.classList.add('d-none');
        scanProgress.style.width = '0%';
        scanStatus.textContent = 'INITIALIZING CAMERA SCANNER...';
        scanModal.classList.add('active');
        addTerminalLog("[Biometrics] Spawning eye calibration modal.");
        
        scanImg.src = '/video_feed';
        
        let progress = 0;
        let progInterval = setInterval(() => {
            if (progress < 92) {
                progress += 3.0;
                scanProgress.style.width = progress + '%';
                
                let msg = 'ALIGNING PUPILS...';
                if (progress > 30 && progress <= 60) msg = 'CALIBRATING baseline ear...';
                else if (progress > 60 && progress <= 80) msg = 'DECODING brain waves...';
                else if (progress > 80) msg = 'DECRYPTING thoughts...';
                
                scanStatus.textContent = `${msg} ${Math.round(progress)}%`;
            }
        }, 120);

        calibrationController = new AbortController();
        try {
            const resp = await fetch('/api/camera/scan_calibration', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: calibrationController.signal
            });
            clearInterval(progInterval);
            const data = await resp.json();
            
            if (data.success) {
                scanProgress.style.width = '100%';
                scanStatus.textContent = 'SCAN COMPLETED SUCCESSFULLY!';
                cachedCalibrationData = data;
                
                // Populate Results view
                document.getElementById('scan-res-id').textContent = data.patient_id;
                document.getElementById('scan-res-name').textContent = data.name;
                document.getElementById('scan-res-age').textContent = data.age;
                document.getElementById('scan-res-room').textContent = data.room_number;
                document.getElementById('scan-res-condition').textContent = data.medical_condition;
                document.getElementById('scan-res-mind-thoughts').textContent = data.mind_thoughts;
                document.getElementById('scan-res-base-ear').textContent = Number(data.baseline_ear).toFixed(3);
                document.getElementById('scan-res-pd-val').textContent = Number(data.pupil_distance).toFixed(1) + ' mm';
                
                setTimeout(() => {
                    scanActiveView.classList.add('d-none');
                    scanResultView.classList.remove('d-none');
                }, 800);
            } else {
                scanStatus.textContent = `Error: ${data.message}`;
            }
        } catch (e) {
            clearInterval(progInterval);
            if (e.name === 'AbortError') {
                scanStatus.textContent = 'Calibration cancelled.';
            } else {
                scanStatus.textContent = 'Webcam calibration server offline.';
            }
        }
    });

    btnApplyScan?.addEventListener('click', () => {
        if (cachedCalibrationData) {
            document.getElementById('reg-patient-id').value = cachedCalibrationData.patient_id;
            document.getElementById('reg-name').value = cachedCalibrationData.name;
            document.getElementById('reg-age').value = cachedCalibrationData.age;
            document.getElementById('reg-room').value = cachedCalibrationData.room_number;
            document.getElementById('reg-condition').value = cachedCalibrationData.medical_condition;
            document.getElementById('reg-mind-thoughts').value = cachedCalibrationData.mind_thoughts;
            
            document.getElementById('cal-res-baseline').textContent = Number(cachedCalibrationData.baseline_ear).toFixed(3);
            document.getElementById('cal-res-thresh').textContent = Number(cachedCalibrationData.ear_threshold).toFixed(3);
            document.getElementById('cal-res-pd').textContent = Number(cachedCalibrationData.pupil_distance).toFixed(1) + ' mm';
            
            document.getElementById('cal-ear-threshold').value = cachedCalibrationData.ear_threshold;
            document.getElementById('cal-baseline-ear').value = cachedCalibrationData.baseline_ear;
            document.getElementById('cal-pupil-distance').value = cachedCalibrationData.pupil_distance;
            document.getElementById('cal-mind-thoughts').value = cachedCalibrationData.mind_thoughts;
            
            document.getElementById('calibration-results-preview').classList.remove('d-none');
        }
        closeCalibration();
    });

    btnCancelScan?.addEventListener('click', () => {
        if (calibrationController) calibrationController.abort();
        closeCalibration();
    });

    function closeCalibration() {
        scanModal.classList.remove('active');
        scanImg.removeAttribute('src');
    }

    // ==========================================
    // Data Export Operations (Excel & PDF)
    // ==========================================
    document.getElementById('export-patients-btn')?.addEventListener('click', () => {
        exportTableToExcel('patients-table', 'CareBlink_Patients_Registry.xlsx');
    });

    document.getElementById('export-logs-btn')?.addEventListener('click', () => {
        exportTableToExcel('history-table', 'CareBlink_Alert_Incident_Logs.xlsx');
    });

    function exportTableToExcel(tableId, filename) {
        try {
            const table = document.getElementById(tableId);
            if (!table) return;
            
            const wb = XLSX.utils.table_to_book(table, { sheet: "Data Sheet" });
            XLSX.writeFile(wb, filename);
            showToast("Excel Export Completed!", "success");
            addTerminalLog(`[Export] Generated spreadsheet file: ${filename}`);
        } catch (e) {
            console.error('Spreadsheet export failed:', e);
            showToast("Spreadsheet Export Failed.", "danger");
        }
    }

    // ==========================================
    // System Terminal Logs (Admin Console)
    // ==========================================
    function addTerminalLog(msg) {
        const timestamp = new Date().toLocaleTimeString();
        const line = `[${timestamp}] ${msg}`;
        appState.systemLogs.push(line);
        if (appState.systemLogs.length > 40) appState.systemLogs.shift();
        
        const term = document.getElementById('admin-logs-terminal');
        if (term) {
            term.innerHTML = appState.systemLogs.map(l => `<div>${escapeHTML(l)}</div>`).join('');
            term.scrollTop = term.scrollHeight;
        }
    }

    async function loadAdminConsole() {
        const adminDb = document.getElementById('admin-db-dialect');
        const activeDialect = sidebarDbDialect?.textContent || 'SQLite (Auto)';
        if (adminDb) adminDb.textContent = activeDialect;
        
        // Populate Admin Operators list
        const opList = document.getElementById('admin-operators-list');
        if (opList) {
            opList.innerHTML = `
                <div class="bg-dark-soft p-3 rounded-3 mb-2 text-start">
                    <strong class="text-white d-block">St. Jude Medical Center</strong>
                    <span class="text-secondary small d-block">Role: Primary Admin</span>
                    <span class="badge bg-success-soft text-success px-2 py-1 rounded mt-2">Active operator</span>
                </div>
                <div class="bg-dark-soft p-3 rounded-3 text-start">
                    <strong class="text-white d-block">Metro General Clinic</strong>
                    <span class="text-secondary small d-block">Role: Doctor Staff</span>
                    <span class="badge bg-dark-soft text-secondary px-2 py-1 rounded mt-2">Standby</span>
                </div>
            `;
        }
        addTerminalLog("[Admin Console] Loaded system environments & operator nodes.");
    }

    // ==========================================
    // Utility Helpers
    // ==========================================
    function showToast(msg, category = 'success') {
        const toastEl = document.getElementById('alert-toast');
        const toastMsg = document.getElementById('toast-message');
        if (toastEl && toastMsg) {
            toastMsg.textContent = msg;
            toastEl.className = `toast align-items-center text-white border-0 bg-${category}`;
            const bsToast = new bootstrap.Toast(toastEl);
            bsToast.show();
        }
    }

    function escapeHTML(str) {
        if (!str) return '';
        return str.replace(/[&<>'"]/g, 
            tag => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;'
            }[tag] || tag)
        );
    }

    // Initial triggers
    appState.pollingInterval = setInterval(checkActiveAlerts, 1500);
    checkActiveAlerts();
    loadPatientSelect();
});
