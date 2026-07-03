/*
  CareBlink - Dashboard JavaScript Controller
  Handles: Tab navigation, camera subprocess control, live API polling,
           Web Audio alarm synthesiser, logs, and patient records.
*/

document.addEventListener('DOMContentLoaded', () => {
    // Current application state
    const appState = {
        activeTab: 'live-dashboard',
        activeAlert: null,
        soundEnabled: true,
        pollingInterval: null,
        audioContext: null,
        buzzerInterval: null,
        cameraRunning: true,
        localLastBlinkTime: 0.0,
        isHighTone: true
    };

    // DOM Elements Cache
    const tabMenuItems = document.querySelectorAll('.menu-item');
    const contentPanels = document.querySelectorAll('.content-panel');
    const tabTitle = document.getElementById('tab-title');
    const tabSubtitle = document.getElementById('tab-subtitle');
    const soundToggleBtn = document.getElementById('sound-toggle-btn');
    const virtualBulb = document.getElementById('virtual-bulb');
    const bulbStatusText = document.getElementById('bulb-status-text');
    const alertBadge = document.getElementById('alert-badge');
    const normalStateView = document.getElementById('normal-state-view');
    const emergencyStateView = document.getElementById('emergency-state-view');
    const dismissAlertBtn = document.getElementById('dismiss-alert-btn');
    const refreshHistoryBtn = document.getElementById('refresh-history-btn');
    const registerPatientForm = document.getElementById('register-patient-form');
    const patientsTableBody = document.querySelector('#patients-table tbody');
    const historyTableBody = document.querySelector('#history-table tbody');
    
    // Dashboard camera control buttons
    const dbCameraStartBtn = document.getElementById('dashboard-camera-start');
    const dbCameraStopBtn = document.getElementById('dashboard-camera-stop');
    const dbCameraStatusBadge = document.getElementById('dashboard-camera-status');
    const sidebarDbDialect = document.getElementById('sidebar-db-dialect');

    // Page metadata
    const pageMetadata = {
        'live-dashboard': {
            title: 'Live Monitor Dashboard',
            subtitle: 'Real-time patient monitoring feed and status alerts.'
        },
        'patient-records': {
            title: 'Patients Registry',
            subtitle: 'Manage and register patient profiles for blink monitoring.'
        },
        'alert-history': {
            title: 'Emergency Incident Logs',
            subtitle: 'Historical archive of eye-blink emergency dispatches.'
        },
        'hospital-records': {
            title: 'All Hospital Records',
            subtitle: 'Isolated medical registries and monitoring archives segmented by facility.'
        }
    };

    // ==========================================================================
    // Sidebar Navigation Tabs Setup
    // ==========================================================================
    tabMenuItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetTab = item.getAttribute('data-tab');
            
            tabMenuItems.forEach(mi => mi.classList.remove('active'));
            item.classList.add('active');

            contentPanels.forEach(panel => panel.classList.remove('active'));
            document.getElementById(`${targetTab}-tab`).classList.add('active');

            tabTitle.textContent = pageMetadata[targetTab].title;
            tabSubtitle.textContent = pageMetadata[targetTab].subtitle;

            appState.activeTab = targetTab;

            if (targetTab === 'patient-records') {
                loadPatientsList();
            } else if (targetTab === 'alert-history') {
                loadAlertHistory();
            } else if (targetTab === 'hospital-records') {
                loadHospitalRecords();
            }
        });
    });

    // Hospital selector tab click listeners for "All Hospital Records"
    const hospitalTabBtns = document.querySelectorAll('.hospital-tab-btn');
    const hospitalSections = document.querySelectorAll('.hospital-section');

    hospitalTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            hospitalTabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const hospId = btn.getAttribute('data-hospital');
            hospitalSections.forEach(sec => {
                if (sec.id === `${hospId}-section`) {
                    sec.classList.add('active');
                } else {
                    sec.classList.remove('active');
                }
            });
        });
    });

    // ==========================================================================
    // Camera Subprocess API Handlers
    // ==========================================================================
    async function updateCameraStatus() {
        try {
            const response = await fetch('/api/camera/status');
            const data = await response.json();
            appState.cameraRunning = data.is_running;
            
            const cameraImg = document.getElementById('camera-stream-img');
            const cameraPlaceholder = document.getElementById('camera-placeholder-box');
            
            const teleName = document.getElementById('tele-patient-name');
            const teleId = document.getElementById('tele-patient-id');
            const teleRoom = document.getElementById('tele-patient-room');
            const teleCondition = document.getElementById('tele-patient-condition');
            const teleEarBase = document.getElementById('tele-ear-base');
            const teleEarCurrent = document.getElementById('tele-ear-current');
            const teleEarThresh = document.getElementById('tele-ear-thresh');
            const telePupilDist = document.getElementById('tele-pupil-dist');
            const teleCurrentPd = document.getElementById('tele-current-pd');
            const teleGazePos = document.getElementById('tele-gaze-pos');
            const teleBlinksCount = document.getElementById('tele-blinks-count');
            const teleSystemStatus = document.getElementById('tele-system-status');
            
            if (appState.cameraRunning) {
                dbCameraStatusBadge.className = 'camera-badge running';
                dbCameraStatusBadge.querySelector('.text').textContent = 'ONLINE';
                dbCameraStartBtn.disabled = true;
                dbCameraStopBtn.disabled = false;
                
                document.getElementById('system-status-badge').querySelector('.status-text').textContent = 'Camera Streaming';
                document.getElementById('system-status-badge').querySelector('.pulse-dot').className = 'pulse-dot green';
                
                if (cameraImg && cameraPlaceholder) {
                    cameraImg.src = '/video_feed';
                    cameraImg.style.display = 'block';
                    cameraPlaceholder.style.display = 'none';
                }
                
                if (teleName && data.patient_name) teleName.textContent = data.patient_name;
                if (teleId && data.patient_id) teleId.textContent = data.patient_id;
                if (teleRoom) {
                    if (data.patient_age && data.room_number) {
                        teleRoom.textContent = `${data.patient_age} / Room ${data.room_number}`;
                    } else if (data.room_number) {
                        teleRoom.textContent = data.room_number;
                    }
                }
                if (teleCondition && data.medical_condition) teleCondition.textContent = data.medical_condition;
                if (teleEarBase && data.baseline_ear !== undefined) teleEarBase.textContent = Number(data.baseline_ear).toFixed(3);
                if (teleEarCurrent && data.current_ear !== undefined) teleEarCurrent.textContent = Number(data.current_ear).toFixed(3);
                if (teleEarThresh && data.ear_threshold !== undefined) teleEarThresh.textContent = Number(data.ear_threshold).toFixed(3);
                if (telePupilDist && data.pupil_distance !== undefined) telePupilDist.textContent = Number(data.pupil_distance).toFixed(1) + ' mm';
                if (teleCurrentPd && data.current_pd !== undefined) teleCurrentPd.textContent = Number(data.current_pd).toFixed(1) + ' mm';
                
                if (teleGazePos && data.current_gaze !== undefined) {
                    teleGazePos.textContent = data.current_gaze.toUpperCase();
                    if (data.current_gaze === 'left' || data.current_gaze === 'right') {
                        teleGazePos.style.color = '#ef4444';
                    } else {
                        teleGazePos.style.color = '#2dd4bf';
                    }
                }
                
                if (teleBlinksCount && data.current_blinks !== undefined) teleBlinksCount.textContent = data.current_blinks;
                
                if (teleSystemStatus) {
                    if (appState.activeAlert) {
                        teleSystemStatus.className = 'status-badge-inline emergency';
                        teleSystemStatus.textContent = 'EMERGENCY';
                    } else if (data.face_detected) {
                        teleSystemStatus.className = 'status-badge-inline safe';
                        teleSystemStatus.textContent = 'EYES DETECTED';
                    } else {
                        teleSystemStatus.className = 'status-badge-inline warning';
                        teleSystemStatus.textContent = 'SEARCHING EYES...';
                    }
                }
                
            } else {
                dbCameraStatusBadge.className = 'camera-badge stopped';
                dbCameraStatusBadge.querySelector('.text').textContent = 'OFFLINE';
                dbCameraStartBtn.disabled = false;
                dbCameraStopBtn.disabled = true;
                
                document.getElementById('system-status-badge').querySelector('.status-text').textContent = 'Camera Stopped';
                document.getElementById('system-status-badge').querySelector('.pulse-dot').className = 'pulse-dot red';
                
                if (cameraImg && cameraPlaceholder) {
                    cameraImg.removeAttribute('src');
                    cameraImg.style.display = 'none';
                    cameraPlaceholder.style.display = 'flex';
                }
            }
        } catch (err) {
            console.error('Error fetching camera status:', err);
        }
    }

    // Minimize button logic for floating camera widget
    const minimizeFloatCamBtn = document.getElementById('minimize-floating-cam');
    const floatWidgetEl = document.getElementById('floating-camera-widget');
    if (minimizeFloatCamBtn && floatWidgetEl) {
        minimizeFloatCamBtn.addEventListener('click', (e) => {
            e.preventDefault();
            floatWidgetEl.classList.toggle('minimized');
            const icon = minimizeFloatCamBtn.querySelector('i');
            if (floatWidgetEl.classList.contains('minimized')) {
                icon.className = 'fa-solid fa-expand';
            } else {
                icon.className = 'fa-solid fa-minus';
            }
        });
    }

    function scrollToCameraFeed() {
        const targetTab = 'live-dashboard';
        const item = document.querySelector(`.menu-item[data-tab="${targetTab}"]`);
        if (item && !item.classList.contains('active')) {
            tabMenuItems.forEach(mi => mi.classList.remove('active'));
            item.classList.add('active');

            contentPanels.forEach(panel => panel.classList.remove('active'));
            document.getElementById(`${targetTab}-tab`).classList.add('active');

            tabTitle.textContent = pageMetadata[targetTab].title;
            tabSubtitle.textContent = pageMetadata[targetTab].subtitle;

            appState.activeTab = targetTab;
        }
        
        // Scroll to the camera stream section
        const cameraCard = document.querySelector('.camera-action-card');
        if (cameraCard) {
            cameraCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    dbCameraStartBtn.addEventListener('click', async () => {
        try {
            dbCameraStartBtn.disabled = true;
            const patientIdVal = document.getElementById('monitor-patient-select')?.value || 'PT-2045';
            const response = await fetch('/api/camera/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ patient_id: patientIdVal })
            });
            const data = await response.json();
            if (data.success) {
                updateCameraStatus();
                setTimeout(scrollToCameraFeed, 150);
            }
        } catch (err) {
            console.error('Camera start failed:', err);
            dbCameraStartBtn.disabled = false;
        }
    });

    dbCameraStopBtn.addEventListener('click', async () => {
        try {
            dbCameraStopBtn.disabled = true;
            const response = await fetch('/api/camera/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();
            if (data.success) {
                updateCameraStatus();
            }
        } catch (err) {
            console.error('Camera stop failed:', err);
            dbCameraStopBtn.disabled = false;
        }
    });

    // Initial check on page load
    updateCameraStatus();
    loadPatientSelect();


    // ==========================================================================
    // Sound & Web Audio API Buzzer Logic
    // ==========================================================================
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
            stopBuzzerBeep();
        }
    });

    function initAudioContext() {
        if (!appState.audioContext) {
            appState.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
    }

    // Play synthesized monitor sounds
    function playSingleBeep(frequency = 980, duration = 0.25, volume = 0.3) {
        if (!appState.soundEnabled) return;
        try {
            initAudioContext();
            const ctx = appState.audioContext;
            
            if (ctx.state === 'suspended') {
                ctx.resume();
            }

            const osc = ctx.createOscillator();
            const gainNode = ctx.createGain();

            osc.connect(gainNode);
            gainNode.connect(ctx.destination);

            osc.type = 'sine';
            osc.frequency.setValueAtTime(frequency, ctx.currentTime);

            gainNode.gain.setValueAtTime(volume, ctx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration);

            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + duration);
        } catch (e) {
            console.error('Audio synthesizer error:', e);
        }
    }

    // Continuous Wailing Ambulance/Hospital Emergency Siren
    function startBuzzerBeep() {
        if (appState.sirenOscillator) return; // already active
        if (!appState.soundEnabled) return;
        
        try {
            initAudioContext();
            const ctx = appState.audioContext;
            if (ctx.state === 'suspended') ctx.resume();

            // Primary wailing oscillator
            const osc = ctx.createOscillator();
            const gainNode = ctx.createGain();

            osc.connect(gainNode);
            gainNode.connect(ctx.destination);

            osc.type = 'sawtooth'; // sawtooth gives a very rich, loud, piercing wail siren tone (big sound!)
            osc.frequency.setValueAtTime(800, ctx.currentTime);

            // Modulating LFO (alternates frequency dynamically for siren wail)
            const lfo = ctx.createOscillator();
            const lfoGain = ctx.createGain();

            lfo.type = 'triangle';
            lfo.frequency.setValueAtTime(2.2, ctx.currentTime); // 2.2 Hz modulation cycle (fast, urgent!)
            lfoGain.gain.setValueAtTime(220, ctx.currentTime);  // Modulate frequency +/- 220 Hz (sweep range 580Hz - 1020Hz)

            // Connect LFO Modulator -> Gain -> Primary Oscillator Frequency
            lfo.connect(lfoGain);
            lfoGain.connect(osc.frequency);

            // Set high volume (0.4 gain) for a big, clear wail
            gainNode.gain.setValueAtTime(0.001, ctx.currentTime);
            gainNode.gain.linearRampToValueAtTime(0.4, ctx.currentTime + 0.08);

            lfo.start();
            osc.start();

            // Store references in appState to terminate later
            appState.sirenOscillator = osc;
            appState.sirenLfo = lfo;
            appState.sirenGain = gainNode;
            
            console.log("[*] Loud continuous wailing siren alarm started.");
        } catch (e) {
            console.error('Failed to start continuous siren:', e);
        }
    }

    function stopBuzzerBeep() {
        if (appState.sirenOscillator) {
            try {
                const ctx = appState.audioContext;
                const osc = appState.sirenOscillator;
                const lfo = appState.sirenLfo;
                const gain = appState.sirenGain;

                // Smooth fade-out to prevent popping sounds
                gain.gain.setValueAtTime(gain.gain.value, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);

                osc.stop(ctx.currentTime + 0.2);
                lfo.stop(ctx.currentTime + 0.2);
                console.log("[-] Wailing siren alarm stopped.");
            } catch (e) {
                console.error('Error stopping siren alarm:', e);
            }
            appState.sirenOscillator = null;
            appState.sirenLfo = null;
            appState.sirenGain = null;
        }
    }


    // ==========================================================================
    // Core Live Polling Engine
    // ==========================================================================
    async function checkActiveAlerts() {
        try {
            const response = await fetch('/api/alerts/active');
            if (!response.ok) throw new Error('Network error');
            const data = await response.json();
            
            // Sync database dialect in sidebar
            if (data.db_dialect) {
                sidebarDbDialect.textContent = data.db_dialect;
            }

            // 1. Play soft beep sound if a new normal blink is detected
            if (data.last_blink_time && data.last_blink_time > appState.localLastBlinkTime) {
                if (appState.localLastBlinkTime > 0.0) {
                    playSingleBeep(520, 0.08, 0.15);
                }
                appState.localLastBlinkTime = data.last_blink_time;
            }

            // 2. Manage Emergency visual states
            if (data.has_active) {
                appState.activeAlert = data.alert;
                renderAlertActive(data.alert);
            } else {
                appState.activeAlert = null;
                renderAlertSafe();
            }
            
            // Sync camera and floating widget telemetry stats
            updateCameraStatus();
        } catch (error) {
            console.error('Error polling active alerts:', error);
            document.getElementById('system-status-badge').querySelector('.status-text').textContent = 'API Connection Error';
            document.getElementById('system-status-badge').querySelector('.pulse-dot').className = 'pulse-dot red';
        }
    }

    function renderAlertActive(alert) {
        normalStateView.classList.add('hidden');
        emergencyStateView.classList.remove('hidden');

        virtualBulb.className = 'virtual-bulb status-emergency';
        bulbStatusText.textContent = 'EMERGENCY ALERT';
        bulbStatusText.className = 'bulb-status-text emergency';
        
        alertBadge.textContent = 'EMERGENCY';
        alertBadge.className = 'badge emergency';

        document.getElementById('emg-patient-name').textContent = alert.name;
        document.getElementById('emg-patient-room').textContent = `${alert.patient_id} / ${alert.room_number}`;
        document.getElementById('emg-patient-condition').textContent = alert.medical_condition;
        document.getElementById('emg-message').textContent = alert.message;
        document.getElementById('emergency-time').textContent = `Triggered at: ${alert.created_at}`;

        startBuzzerBeep();
    }

    function renderAlertSafe() {
        emergencyStateView.classList.add('hidden');
        normalStateView.classList.remove('hidden');

        alertBadge.textContent = 'NORMAL';
        alertBadge.className = 'badge';

        stopBuzzerBeep();
        
        if (appState.cameraRunning) {
            virtualBulb.className = 'virtual-bulb status-safe';
            bulbStatusText.textContent = 'SYSTEM SECURE';
            bulbStatusText.className = 'bulb-status-text';
            
            document.getElementById('system-status-badge').querySelector('.status-text').textContent = 'Camera Streaming';
            document.getElementById('system-status-badge').querySelector('.pulse-dot').className = 'pulse-dot green';
        } else {
            virtualBulb.className = 'virtual-bulb status-warning';
            bulbStatusText.textContent = 'CAMERA OFFLINE';
            bulbStatusText.className = 'bulb-status-text warning';
            
            document.getElementById('system-status-badge').querySelector('.status-text').textContent = 'Camera Stopped';
            document.getElementById('system-status-badge').querySelector('.pulse-dot').className = 'pulse-dot red';
        }
    }

    dismissAlertBtn.addEventListener('click', async () => {
        try {
            stopBuzzerBeep();
            renderAlertSafe();
            
            await fetch('/api/alerts/dismiss', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
        } catch (err) {
            console.error('Network error during dismiss:', err);
        }
    });

    // Start Polling loop (every 1.5 seconds)
    appState.pollingInterval = setInterval(checkActiveAlerts, 1500);
    // Initial run
    checkActiveAlerts();


    // ==========================================================================
    // Patient Registration and Registry Tab
    // ==========================================================================
    registerPatientForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const payload = {
            patient_id: document.getElementById('reg-patient-id').value.trim(),
            name: document.getElementById('reg-name').value.trim(),
            age: parseInt(document.getElementById('reg-age').value),
            room_number: document.getElementById('reg-room').value.trim(),
            medical_condition: document.getElementById('reg-condition').value.trim(),
            ear_threshold: parseFloat(document.getElementById('cal-ear-threshold')?.value || 0.22),
            baseline_ear: parseFloat(document.getElementById('cal-baseline-ear')?.value || 0.28),
            pupil_distance: parseFloat(document.getElementById('cal-pupil-distance')?.value || 60.0)
        };

        try {
            const response = await fetch('/api/patients', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            
            if (data.success) {
                const banner = document.getElementById('registration-feedback');
                banner.className = 'alert-box alert-success';
                banner.querySelector('span').textContent = 'Patient successfully registered in database!';
                
                registerPatientForm.reset();
                
                // Hide calibration preview card
                const preview = document.getElementById('calibration-results-preview');
                if (preview) {
                    preview.classList.add('hidden');
                    document.getElementById('cal-ear-threshold').value = "0.22";
                    document.getElementById('cal-baseline-ear').value = "0.28";
                    document.getElementById('cal-pupil-distance').value = "60.0";
                }
                
                loadPatientsList();
                loadPatientSelect();

                setTimeout(() => {
                    banner.classList.add('hidden');
                }, 3000);
            } else {
                alert(`Error: ${data.message}`);
            }
        } catch (error) {
            console.error('Error submitting patient registration:', error);
            alert('Failed to connect to Flask API.');
        }
    });

    async function loadPatientsList() {
        try {
            patientsTableBody.innerHTML = '<tr><td colspan="5" class="text-center text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Loading registered patients...</td></tr>';
            
            const response = await fetch('/api/patients');
            if (!response.ok) throw new Error('Failed to retrieve patients');
            const list = await response.json();
            
            if (list.length === 0) {
                patientsTableBody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No patients registered in CareBlink yet.</td></tr>';
                return;
            }

            patientsTableBody.innerHTML = '';
            list.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${escapeHTML(p.patient_id)}</strong></td>
                    <td>${escapeHTML(p.name)}</td>
                    <td>${escapeHTML(String(p.age))}</td>
                    <td><span class="badge">${escapeHTML(p.room_number)}</span></td>
                    <td><span class="text-muted">${escapeHTML(p.medical_condition)}</span></td>
                `;
                patientsTableBody.appendChild(tr);
            });
        } catch (err) {
            console.error('Error fetching patients:', err);
            patientsTableBody.innerHTML = '<tr><td colspan="5" class="text-center alert-text">Failed to connect to patient directory api.</td></tr>';
        }
    }


    // ==========================================================================
    // Incident Logs / Alert History Tab
    // ==========================================================================
    refreshHistoryBtn.addEventListener('click', loadAlertHistory);

    async function loadAlertHistory() {
        try {
            historyTableBody.innerHTML = '<tr><td colspan="7" class="text-center text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Fetching recent alerts from MySQL...</td></tr>';
            
            const response = await fetch('/api/alerts/history');
            if (!response.ok) throw new Error('History fetch error');
            const data = await response.json();
            
            if (data.length === 0) {
                historyTableBody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No alarm history logs found.</td></tr>';
                return;
            }

            historyTableBody.innerHTML = '';
            data.forEach(log => {
                const tr = document.createElement('tr');
                let statusBadge = '';
                if (log.status === 'active') {
                    statusBadge = '<span class="status-indicator active"><i class="fa-solid fa-bell fa-shake"></i> Active</span>';
                } else {
                    statusBadge = '<span class="status-indicator dismissed"><i class="fa-solid fa-check-double"></i> Dismissed</span>';
                }

                tr.innerHTML = `
                    <td>${escapeHTML(log.created_at)}</td>
                    <td><strong>${escapeHTML(log.patient_id)}</strong></td>
                    <td>${escapeHTML(log.name)}</td>
                    <td><span class="badge">${escapeHTML(log.room_number)}</span></td>
                    <td>${escapeHTML(log.message)}</td>
                    <td>${statusBadge}</td>
                    <td>${escapeHTML(log.resolved_at)}</td>
                `;
                historyTableBody.appendChild(tr);
            });
        } catch (error) {
            console.error('Error fetching history logs:', error);
            historyTableBody.innerHTML = '<tr><td colspan="7" class="text-center alert-text">Failed to fetch alerts log history from server.</td></tr>';
        }
    }

    async function loadPatientSelect() {
        const selectEl = document.getElementById('monitor-patient-select');
        if (!selectEl) return;
        try {
            const response = await fetch('/api/patients');
            if (!response.ok) throw new Error('Failed to load patients');
            const patients = await response.json();
            
            selectEl.innerHTML = '';
            patients.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.patient_id;
                opt.textContent = `${p.name} (${p.room_number})`;
                selectEl.appendChild(opt);
            });
        } catch (err) {
            console.error('Error loading patient select:', err);
        }
    }

    async function loadHospitalRecords() {
        const hospTitle = document.getElementById('hosp-records-title');
        const hospProfileName = document.getElementById('hosp-profile-name');
        const hospProfileState = document.getElementById('hosp-profile-state');
        const hospProfilePatientsCount = document.getElementById('hosp-profile-patients-count');
        const hospProfileAlertsCount = document.getElementById('hosp-profile-alerts-count');
        const hospPatientsTableBody = document.querySelector('#hosp-patients-table tbody');
        const hospVideosTableBody = document.querySelector('#hosp-videos-table tbody');
        
        try {
            if (hospPatientsTableBody) hospPatientsTableBody.innerHTML = '<tr><td colspan="4" class="text-center text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</td></tr>';
            if (hospVideosTableBody) hospVideosTableBody.innerHTML = '<tr><td colspan="5" class="text-center text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</td></tr>';
            
            const response = await fetch('/api/hospital/records');
            if (!response.ok) throw new Error('Failed to load hospital records');
            const data = await response.json();
            
            // Set header & profile details
            if (hospTitle) hospTitle.textContent = `${data.hospital_name} - Records Archive`;
            if (hospProfileName) hospProfileName.textContent = data.hospital_name;
            if (hospProfileState) hospProfileState.textContent = data.state;
            if (hospProfilePatientsCount) hospProfilePatientsCount.textContent = `${data.patients.length} Patients Registered`;
            if (hospProfileAlertsCount) hospProfileAlertsCount.textContent = `${data.alerts.length} Incidents Logged`;
            
            // Populate patients table
            if (hospPatientsTableBody) {
                if (data.patients.length === 0) {
                    hospPatientsTableBody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No patients registered for this hospital.</td></tr>';
                } else {
                    hospPatientsTableBody.innerHTML = '';
                    data.patients.forEach(p => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><strong>${escapeHTML(p.patient_id)}</strong></td>
                            <td>${escapeHTML(p.name)}</td>
                            <td><span class="badge">${escapeHTML(p.room_number)}</span></td>
                            <td><span class="text-muted">${escapeHTML(p.medical_condition)}</span></td>
                        `;
                        hospPatientsTableBody.appendChild(tr);
                    });
                }
            }
            
            // Populate video and alert history table
            if (hospVideosTableBody) {
                if (data.alerts.length === 0) {
                    hospVideosTableBody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No alerts or recorded clips found.</td></tr>';
                } else {
                    hospVideosTableBody.innerHTML = '';
                    data.alerts.forEach(a => {
                        const tr = document.createElement('tr');
                        
                        let videoCell = '<span class="text-muted"><i class="fa-solid fa-video-slash"></i> No Clip</span>';
                        if (a.video_filename) {
                            videoCell = `
                                <a href="/all_records/${escapeHTML(a.video_filename)}" target="_blank" class="action-btn btn-secondary btn-ripple" style="padding: 4px 10px; font-size: 0.75rem; border-radius: 6px;">
                                    <i class="fa-solid fa-circle-play text-danger"></i> Watch Video
                                </a>
                            `;
                        }
                        
                        tr.innerHTML = `
                            <td>${escapeHTML(a.created_at)}</td>
                            <td><strong>${escapeHTML(a.patient_id)}</strong></td>
                            <td>${escapeHTML(a.name)}</td>
                            <td>${escapeHTML(a.message)}</td>
                            <td>${videoCell}</td>
                        `;
                        hospVideosTableBody.appendChild(tr);
                    });
                }
            }
            
        } catch (err) {
            console.error('Error fetching hospital records:', err);
            if (hospPatientsTableBody) hospPatientsTableBody.innerHTML = '<tr><td colspan="4" class="text-center alert-text">Failed to fetch patient data.</td></tr>';
            if (hospVideosTableBody) hospVideosTableBody.innerHTML = '<tr><td colspan="5" class="text-center alert-text">Failed to fetch video telemetry clips.</td></tr>';
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
    // ==========================================================================
    // Eye Calibration Scan Controller
    // ==========================================================================
    const btnScanPatient = document.getElementById('btn-scan-patient');
    const eyeScanModal = document.getElementById('eye-scan-modal');
    const btnCancelScan = document.getElementById('btn-cancel-scan');
    const btnApplyScan = document.getElementById('btn-apply-scan');
    const scanStreamImg = document.getElementById('scan-stream-img');
    const scanProgressBar = document.getElementById('scan-progress-bar');
    const scanStatusText = document.getElementById('scan-status-text');
    
    const scanActiveView = document.getElementById('scan-active-view');
    const scanResultView = document.getElementById('scan-result-view');
    
    let scanController = null;
    let lastScanData = null;
    
    if (btnScanPatient && eyeScanModal) {
        btnScanPatient.addEventListener('click', async () => {
            // Reset scan state
            scanActiveView.classList.remove('hidden');
            scanResultView.classList.add('hidden');
            scanProgressBar.style.width = '0%';
            scanStatusText.textContent = 'INITIALIZING WEBCAM SCANNER...';
            eyeScanModal.classList.add('active');
            
            // Set stream source to active feed
            scanStreamImg.src = '/video_feed';
            
            let progress = 0;
            let progressInterval = setInterval(() => {
                if (progress < 90) {
                    progress += 2.5;
                    scanProgressBar.style.width = progress + '%';
                    scanStatusText.textContent = `ANALYZING EYE REFLECTION & GEOMETRY... ${Math.round(progress)}%`;
                }
            }, 100);
            
            scanController = new AbortController();
            const signal = scanController.signal;
            
            try {
                const response = await fetch('/api/camera/scan_calibration', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    signal: signal
                });
                
                clearInterval(progressInterval);
                const data = await response.json();
                
                if (data.success) {
                    scanProgressBar.style.width = '100%';
                    scanStatusText.textContent = 'BIOMETRIC SCAN COMPLETE!';
                    
                    lastScanData = data;
                    
                    // Show scanned details inside result view
                    document.getElementById('scan-res-id').textContent = data.patient_id;
                    document.getElementById('scan-res-name').textContent = data.name;
                    document.getElementById('scan-res-age').textContent = data.age;
                    document.getElementById('scan-res-room').textContent = data.room_number;
                    document.getElementById('scan-res-condition').textContent = data.medical_condition;
                    document.getElementById('scan-res-base-ear').textContent = data.baseline_ear.toFixed(3);
                    document.getElementById('scan-res-pd-val').textContent = data.pupil_distance.toFixed(1) + ' mm';
                    
                    setTimeout(() => {
                        scanActiveView.classList.add('hidden');
                        scanResultView.classList.remove('hidden');
                    }, 600);
                } else {
                    scanStatusText.textContent = `SCAN FAILED: ${data.message}`;
                    scanProgressBar.style.width = '0%';
                }
            } catch (err) {
                clearInterval(progressInterval);
                if (err.name === 'AbortError') {
                    scanStatusText.textContent = 'CALIBRATION CANCELLED.';
                } else {
                    scanStatusText.textContent = 'ERROR: Webcam server offline.';
                    console.error('Calibration scan failed:', err);
                }
                scanProgressBar.style.width = '0%';
            }
        });
        
        if (btnApplyScan) {
            btnApplyScan.addEventListener('click', () => {
                if (lastScanData) {
                    // Populate fields
                    document.getElementById('reg-patient-id').value = lastScanData.patient_id;
                    document.getElementById('reg-name').value = lastScanData.name;
                    document.getElementById('reg-age').value = lastScanData.age;
                    document.getElementById('reg-room').value = lastScanData.room_number;
                    document.getElementById('reg-condition').value = lastScanData.medical_condition;
                    
                    // Update preview values
                    document.getElementById('cal-res-baseline').textContent = lastScanData.baseline_ear.toFixed(3);
                    document.getElementById('cal-res-thresh').textContent = lastScanData.ear_threshold.toFixed(3);
                    document.getElementById('cal-res-pd').textContent = lastScanData.pupil_distance.toFixed(1) + ' mm';
                    
                    // Set hidden inputs
                    document.getElementById('cal-ear-threshold').value = lastScanData.ear_threshold;
                    document.getElementById('cal-baseline-ear').value = lastScanData.baseline_ear;
                    document.getElementById('cal-pupil-distance').value = lastScanData.pupil_distance;
                    
                    // Show preview
                    document.getElementById('calibration-results-preview').classList.remove('hidden');
                }
                closeScanModal();
            });
        }
        
        btnCancelScan.addEventListener('click', () => {
            if (scanController) {
                scanController.abort();
            }
            closeScanModal();
        });
        
        function closeScanModal() {
            eyeScanModal.classList.remove('active');
            scanStreamImg.removeAttribute('src');
        }
    }
});
