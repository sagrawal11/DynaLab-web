document.addEventListener('DOMContentLoaded', function() {
    // Get all form elements
    const pdbFileInput = document.getElementById('pdb-file');
    const fileInfo = document.getElementById('file-info');
    const userName = document.getElementById('user-name');
    const userEmail = document.getElementById('user-email');
    const simMode = document.getElementById('sim-mode');
    const duration = document.getElementById('duration');
    const frameInterval = document.getElementById('frame-interval');
    const temperature = document.getElementById('temperature');
    const nReplicas = document.getElementById('n-replicas');
    const tempLow = document.getElementById('temp-low');
    const tempHigh = document.getElementById('temp-high');
    const replicaInterval = document.getElementById('replica-interval');
    const membraneCoordSystem = document.getElementById('membrane-coord-system');
    const membraneInner = document.getElementById('membrane-inner');
    const membraneOuter = document.getElementById('membrane-outer');
    const disableRecentering = document.getElementById('disable-recentering');
    const disableZRecentering = document.getElementById('disable-z-recentering');
    const runBtn = document.getElementById('run-btn');
    const configSummary = document.getElementById('config-summary');
    const progressSection = document.getElementById('progress-section');
    const resultsSection = document.getElementById('results-section');
    const analysisSection = document.getElementById('analysis-section');
    const runAnalysisBtn = document.getElementById('run-analysis-btn');
    const analysisStatusEl = document.getElementById('analysis-status');
    const analysisResultsEl = document.getElementById('analysis-results');
    const modeDescription = document.getElementById('mode-description');

    let currentJobId = null;

    // Get card elements and toggles
    const constTempParams = document.getElementById('const-temp-params');
    const replicaParams = document.getElementById('replica-params');
    const enablePulling = document.getElementById('enable-pulling');
    const pullingContent = document.getElementById('pulling-content');
    const enableMembrane = document.getElementById('enable-membrane');
    const membraneContent = document.getElementById('membrane-content');
    const enableRestraints = document.getElementById('enable-restraints');
    const restraintsContent = document.getElementById('restraints-content');

    // Get restraint text areas
    const wallConstText = document.getElementById('wall-const-text');
    const wallPairText = document.getElementById('wall-pair-text');
    const springConstText = document.getElementById('spring-const-text');
    const springPairText = document.getElementById('spring-pair-text');
    const nailText = document.getElementById('nail-text');

    // Get add buttons
    const addAfmBtn = document.getElementById('add-afm-btn');

    let selectedFile = null;
    let currentConfig = {};

    const modeDescriptions = {
        'constant': 'Standard molecular dynamics at constant temperature.',
        'replica': 'Replica exchange MD for enhanced sampling across temperature range.'
    };

    // Initialize UI
    updateSliderValues();
    updateConfigSummary();
    updateCardVisibility();
    setupEventListeners();

    function setupEventListeners() {
        // File upload handling
        pdbFileInput.addEventListener('change', handleFileUpload);

        // Contact details
        userName.addEventListener('input', updateConfigSummary);
        userEmail.addEventListener('input', updateConfigSummary);
        userName.addEventListener('input', updateRunButton);
        userEmail.addEventListener('input', updateRunButton);

        // Simulation mode
        simMode.addEventListener('change', function() {
            modeDescription.textContent = modeDescriptions[this.value];
            updateCardVisibility();
            updateConfigSummary();
        });

        // Sliders
        [duration, frameInterval, temperature, nReplicas, tempLow, tempHigh, replicaInterval, membraneInner, membraneOuter].forEach(slider => {
            slider.addEventListener('input', function() {
                updateSliderValues();
                updateConfigSummary();
            });
        });

        // Membrane coordinate system
        membraneCoordSystem.addEventListener('change', updateConfigSummary);

        // Card toggles
        enablePulling.addEventListener('change', function() {
            toggleCardContent(pullingContent, this.checked);
            updateConfigSummary();
        });

        enableMembrane.addEventListener('change', function() {
            toggleCardContent(membraneContent, this.checked);
            updateConfigSummary();
        });

        enableRestraints.addEventListener('change', function() {
            toggleCardContent(restraintsContent, this.checked);
            updateConfigSummary();
        });

        // Membrane options
        disableRecentering.addEventListener('change', updateConfigSummary);
        disableZRecentering.addEventListener('change', updateConfigSummary);

        // Restraint text areas
        if (wallConstText) wallConstText.addEventListener('input', updateConfigSummary);
        if (wallPairText) wallPairText.addEventListener('input', updateConfigSummary);
        if (springConstText) springConstText.addEventListener('input', updateConfigSummary);
        if (springPairText) springPairText.addEventListener('input', updateConfigSummary);
        if (nailText) nailText.addEventListener('input', updateConfigSummary);

        // Restraint checkbox handlers
        const enableWallConst = document.getElementById('enable-wall-const');
        const enableWallPair = document.getElementById('enable-wall-pair');
        const enableSpringConst = document.getElementById('enable-spring-const');
        const enableSpringPair = document.getElementById('enable-spring-pair');
        const enableNail = document.getElementById('enable-nail');

        if (enableWallConst) {
            enableWallConst.addEventListener('change', function() {
                const entries = document.getElementById('wall-const-entries');
                if (entries) {
                    if (this.checked) {
                        entries.classList.remove('hidden');
                    } else {
                        entries.classList.add('hidden');
                    }
                }
                updateConfigSummary();
            });
        }

        if (enableWallPair) {
            enableWallPair.addEventListener('change', function() {
                const entries = document.getElementById('wall-pair-entries');
                if (entries) {
                    if (this.checked) {
                        entries.classList.remove('hidden');
                    } else {
                        entries.classList.add('hidden');
                    }
                }
                updateConfigSummary();
            });
        }

        if (enableSpringConst) {
            enableSpringConst.addEventListener('change', function() {
                const entries = document.getElementById('spring-const-entries');
                if (entries) {
                    if (this.checked) {
                        entries.classList.remove('hidden');
                    } else {
                        entries.classList.add('hidden');
                    }
                }
                updateConfigSummary();
            });
        }

        if (enableSpringPair) {
            enableSpringPair.addEventListener('change', function() {
                const entries = document.getElementById('spring-pair-entries');
                if (entries) {
                    if (this.checked) {
                        entries.classList.remove('hidden');
                    } else {
                        entries.classList.add('hidden');
                    }
                }
                updateConfigSummary();
            });
        }

        if (enableNail) {
            enableNail.addEventListener('change', function() {
                const entries = document.getElementById('nail-entries');
                if (entries) {
                    if (this.checked) {
                        entries.classList.remove('hidden');
                    } else {
                        entries.classList.add('hidden');
                    }
                }
                updateConfigSummary();
            });
        }

        // Add buttons
        addAfmBtn.addEventListener('click', addAfmEntry);

        // Run button
        runBtn.addEventListener('click', runSimulation);

        // Analysis button
        if (runAnalysisBtn) {
            runAnalysisBtn.addEventListener('click', runAnalysis);
        }

        // Keep clicking the PCA n_components input from toggling its parent <label>
        const pcaInput = document.getElementById('pca-n-components');
        if (pcaInput) {
            ['click', 'mousedown', 'keydown'].forEach(ev => {
                pcaInput.addEventListener(ev, e => e.stopPropagation());
            });
        }

        // Setup initial remove button handlers
        setupRemoveHandlers();
    }

    function handleFileUpload(e) {
        const file = e.target.files[0];
        if (file) {
            selectedFile = file;
            fileInfo.innerHTML = `
                <strong>Selected:</strong> ${file.name} (${(file.size / 1024).toFixed(1)} KB)
                <br><strong>Type:</strong> ${file.type || 'PDB structure file'}
            `;
            fileInfo.classList.remove('hidden');
            updateRunButton();
        }
    }

    function updateSliderValues() {
        document.getElementById('duration-value').textContent = duration.value;
        document.getElementById('frame-value').textContent = frameInterval.value;
        document.getElementById('temp-value').textContent = temperature.value;
        document.getElementById('replicas-value').textContent = nReplicas.value;
        document.getElementById('temp-low-value').textContent = tempLow.value;
        document.getElementById('temp-high-value').textContent = tempHigh.value;
        document.getElementById('replica-interval-value').textContent = replicaInterval.value;
        document.getElementById('inner-value').textContent = membraneInner.value;
        document.getElementById('outer-value').textContent = membraneOuter.value;
    }

    function updateCardVisibility() {
        const selectedMode = simMode.value;

        if (selectedMode === 'replica') {
            constTempParams.classList.add('hidden');
            replicaParams.classList.remove('hidden');
        } else {
            constTempParams.classList.remove('hidden');
            replicaParams.classList.add('hidden');
        }
    }

    function toggleCardContent(content, enabled) {
        if (enabled) {
            content.classList.remove('disabled');
        } else {
            content.classList.add('disabled');
        }
    }


    function addAfmEntry() {
        const afmEntries = document.getElementById('afm-entries');
        const entryCount = afmEntries.children.length + 1;
        const newEntry = document.createElement('div');
        newEntry.className = 'afm-entry';
        newEntry.innerHTML = `
            <div class="afm-entry-header">
                <h4>AFM Point ${entryCount}</h4>
            </div>
            <div class="afm-content">
                <div class="afm-row">
                    <div class="afm-field">
                        <label>Residue</label>
                        <input type="number" class="afm-residue" min="0" value="0" placeholder="0">
                    </div>
                    <div class="afm-field">
                        <label>Spring Constant</label>
                        <input type="number" class="afm-spring" step="0.01" value="0.05" placeholder="0.05">
                    </div>
                </div>
                <div class="afm-row">
                    <div class="afm-field">
                        <label>Tip Position (x,y,z)</label>
                        <div class="xyz-compact">
                            <input type="number" class="afm-tip-x" step="0.1" value="0" placeholder="x">
                            <input type="number" class="afm-tip-y" step="0.1" value="0" placeholder="y">
                            <input type="number" class="afm-tip-z" step="0.1" value="0" placeholder="z">
                        </div>
                    </div>
                    <div class="afm-field">
                        <label>Pulling Velocity (x,y,z)</label>
                        <div class="xyz-compact">
                            <input type="number" class="afm-vel-x" step="0.001" value="0" placeholder="vx">
                            <input type="number" class="afm-vel-y" step="0.001" value="0" placeholder="vy">
                            <input type="number" class="afm-vel-z" step="0.001" value="-0.001" placeholder="vz">
                        </div>
                    </div>
                </div>
                <button type="button" class="remove-afm-btn">Remove</button>
            </div>
        `;
        afmEntries.appendChild(newEntry);
        setupRemoveHandlers();
        updateConfigSummary();
    }


    function setupRemoveHandlers() {
        // AFM remove buttons
        document.querySelectorAll('.remove-afm-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                this.closest('.afm-entry').remove();
                updateConfigSummary();
            });
        });

        // Add input listeners for AFM entries
        document.querySelectorAll('.afm-entry input').forEach(input => {
            input.addEventListener('input', updateConfigSummary);
        });
    }

    function updateConfigSummary() {
        currentConfig = {
            userName: userName.value || 'Not specified',
            userEmail: userEmail.value || 'Not specified',
            simMode: simMode.value,
            duration: parseInt(duration.value),
            frameInterval: parseInt(frameInterval.value),
            temperature: parseFloat(temperature.value),
            nReplicas: parseInt(nReplicas.value),
            tempLow: parseFloat(tempLow.value),
            tempHigh: parseFloat(tempHigh.value),
            replicaInterval: parseInt(replicaInterval.value),
            membraneCoordSystem: membraneCoordSystem.value,
            membraneInner: parseFloat(membraneInner.value),
            membraneOuter: parseFloat(membraneOuter.value),
            enablePulling: enablePulling.checked,
            enableMembrane: enableMembrane.checked,
            enableRestraints: enableRestraints.checked,
            disableRecentering: disableRecentering.checked,
            disableZRecentering: disableZRecentering.checked
        };

        let summary = `Contact: ${currentConfig.userName} (${currentConfig.userEmail})
Simulation Mode: ${simMode.options[simMode.selectedIndex].text}
Duration: ${currentConfig.duration} steps (~${(currentConfig.duration * 0.05).toFixed(1)} ns)
Frame Interval: ${currentConfig.frameInterval} steps
Force Field: ff_2.1`;

        // Add temperature info
        if (currentConfig.simMode === 'replica') {
            summary += `
Replicas: ${currentConfig.nReplicas}
Temperature Range: ${currentConfig.tempLow} - ${currentConfig.tempHigh}
Replica Interval: ${currentConfig.replicaInterval} steps`;
        } else {
            summary += `
Temperature: ${currentConfig.temperature}`;
        }

        // Add pulling info
        if (currentConfig.enablePulling) {
            const afmEntries = document.querySelectorAll('.afm-entry');
            summary += `
Pulling: Enabled (${afmEntries.length} AFM points)`;

            afmEntries.forEach((entry, index) => {
                const residue = entry.querySelector('.afm-residue').value;
                const spring = entry.querySelector('.afm-spring').value;
                const tipX = entry.querySelector('.afm-tip-x').value;
                const tipY = entry.querySelector('.afm-tip-y').value;
                const tipZ = entry.querySelector('.afm-tip-z').value;
                const velX = entry.querySelector('.afm-vel-x').value;
                const velY = entry.querySelector('.afm-vel-y').value;
                const velZ = entry.querySelector('.afm-vel-z').value;

                summary += `
  AFM ${index + 1}: Res ${residue}, k=${spring}, tip=(${tipX},${tipY},${tipZ}), vel=(${velX},${velY},${velZ})`;
            });
        }

        // Add membrane info
        if (currentConfig.enableMembrane) {
            const coordLabel = currentConfig.membraneCoordSystem === 'cartesian' ? 'z' : 'h';
            summary += `
Membrane: Enabled (${currentConfig.membraneCoordSystem})
${coordLabel} range: ${currentConfig.membraneInner} to ${currentConfig.membraneOuter} Å`;
            if (currentConfig.disableRecentering) {
                summary += `
Disable recentering: Yes`;
            }
            if (currentConfig.disableZRecentering) {
                summary += `
Disable Z-recentering: Yes`;
            }
        }

        // Add restraint info
        if (currentConfig.enableRestraints) {
            const restraintTypes = [];

            if (wallConstText && wallConstText.value.trim()) {
                const lines = wallConstText.value.trim().split('\n').filter(line => line.trim());
                restraintTypes.push(`Fixed Wall (${lines.length})`);
            }

            if (wallPairText && wallPairText.value.trim()) {
                const lines = wallPairText.value.trim().split('\n').filter(line => line.trim());
                restraintTypes.push(`Pair Wall (${lines.length})`);
            }

            if (springConstText && springConstText.value.trim()) {
                const lines = springConstText.value.trim().split('\n').filter(line => line.trim());
                restraintTypes.push(`Fixed Spring (${lines.length})`);
            }

            if (springPairText && springPairText.value.trim()) {
                const lines = springPairText.value.trim().split('\n').filter(line => line.trim());
                restraintTypes.push(`Pair Spring (${lines.length})`);
            }

            if (nailText && nailText.value.trim()) {
                const lines = nailText.value.trim().split('\n').filter(line => line.trim());
                restraintTypes.push(`Nail (${lines.length})`);
            }

            if (restraintTypes.length > 0) {
                summary += `
Restraints: ${restraintTypes.join(', ')}`;
            }
        }

        configSummary.textContent = summary;
    }

    function updateRunButton() {
        const hasRequiredFields = selectedFile && userName.value.trim() && userEmail.value.trim();
        runBtn.disabled = !hasRequiredFields;
    }

    function runSimulation() {
        if (!selectedFile || !userName.value.trim() || !userEmail.value.trim()) return;

        runBtn.disabled = true;
        runBtn.querySelector('.spinner').classList.remove('hidden');
        runBtn.querySelector('.btn-text').textContent = 'Running...';

        progressSection.classList.remove('hidden');
        resultsSection.classList.add('hidden');
        analysisSection.classList.add('hidden');
        analysisResultsEl.innerHTML = '';
        analysisStatusEl.textContent = '';
        document.getElementById('log-output').textContent = '';

        const afmEntries = Array.from(document.querySelectorAll('.afm-entry')).map(entry => ({
            residue: entry.querySelector('.afm-residue').value,
            spring:  entry.querySelector('.afm-spring').value,
            velX:    entry.querySelector('.afm-vel-x').value,
            velY:    entry.querySelector('.afm-vel-y').value,
            velZ:    entry.querySelector('.afm-vel-z').value
        }));

        const config = {
            duration: parseInt(duration.value),
            frameInterval: parseInt(frameInterval.value),
            temperature: parseFloat(temperature.value),
            enablePulling: enablePulling.checked,
            afmEntries: afmEntries
        };

        const formData = new FormData();
        formData.append('pdb', selectedFile);
        formData.append('config', JSON.stringify(config));

        fetch('/api/jobs', { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                startTimer();
                pollJobStatus(data.job_id);
            })
            .catch(err => {
                document.getElementById('progress-text').textContent = 'Submission failed: ' + err.message;
                resetRunButton();
            });
    }

    let _timerInterval = null;
    let _timerStart = null;

    function startTimer() {
        _timerStart = Date.now();
        const el = document.getElementById('elapsed-time');
        _timerInterval = setInterval(() => {
            const s = ((Date.now() - _timerStart) / 1000).toFixed(1);
            el.textContent = `Time: ${s}s`;
        }, 50);
    }

    function stopTimer() {
        if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; }
    }

    function pollJobStatus(jobId) {
        const progressFill = document.getElementById('progress-fill');
        const progressText = document.getElementById('progress-text');
        const currentStepEl = document.getElementById('current-step');

        fetch('/api/jobs/' + jobId)
            .then(r => r.json())
            .then(data => {
                if (data.status === 'queued') {
                    progressText.textContent = 'Queued...';
                    progressFill.style.width = '2%';
                    currentStepEl.textContent = 'Step: 0';
                    setTimeout(() => pollJobStatus(jobId), 500);
                } else if (data.status === 'running') {
                    const pct = data.total_steps > 0
                        ? Math.min(99, Math.round((data.current_step / data.total_steps) * 100))
                        : 50;
                    progressFill.style.width = pct + '%';
                    progressText.textContent = `Running... ${pct}%`;
                    currentStepEl.textContent = `Step: ${data.current_step} / ${data.total_steps}`;
                    setTimeout(() => pollJobStatus(jobId), 500);
                } else if (data.status === 'completed') {
                    stopTimer();
                    progressFill.style.width = '100%';
                    progressText.textContent = 'Simulation complete!';
                    currentStepEl.textContent = `Step: ${data.total_steps} / ${data.total_steps}`;
                    displayResults(jobId);
                } else if (data.status === 'failed') {
                    stopTimer();
                    progressText.textContent = `Failed${data.returncode != null ? ' (exit ' + data.returncode + ')' : ''}: ${data.error || 'check server log'}`;
                    progressFill.style.width = '100%';
                    resetRunButton();
                }
            })
            .catch(err => {
                progressText.textContent = 'Status check failed: ' + err.message;
                resetRunButton();
            });
    }

    function displayResults(jobId) {
        currentJobId = jobId;
        runBtn.querySelector('.spinner').classList.add('hidden');
        runBtn.querySelector('.btn-text').textContent = 'Run Complete';
        resultsSection.classList.remove('hidden');
        analysisSection.classList.remove('hidden');
        analysisResultsEl.innerHTML = '';
        analysisStatusEl.textContent = '';

        document.getElementById('traj-filename').textContent = `${jobId}.run.up`;
        document.getElementById('result-summary').textContent =
            `Job ID: ${jobId}\nTrajectory: ${jobId}.run.up\nDownload via the button below.`;

        document.querySelectorAll('.download-btn').forEach(btn => {
            btn.onclick = () => { window.location = '/api/jobs/' + jobId + '/download'; };
        });

        setTimeout(resetRunButton, 1500);
    }

    function resetRunButton() {
        runBtn.disabled = false;
        runBtn.querySelector('.spinner').classList.add('hidden');
        runBtn.querySelector('.btn-text').textContent = 'Run Simulation';
    }

    function runAnalysis() {
        if (!currentJobId) return;

        const selected = Array.from(
            document.querySelectorAll('input[name="analysis"]:checked')
        ).map(cb => cb.value);

        if (selected.length === 0) {
            analysisStatusEl.textContent = 'Pick at least one analysis to run.';
            return;
        }

        const params = {};
        if (selected.includes('pca')) {
            const nInput = document.getElementById('pca-n-components');
            const n = parseInt(nInput && nInput.value, 10);
            if (Number.isFinite(n) && n >= 1) {
                params.pca = { n_components: n };
            }
        }

        runAnalysisBtn.disabled = true;
        runAnalysisBtn.querySelector('.spinner').classList.remove('hidden');
        runAnalysisBtn.querySelector('.btn-text').textContent = 'Analyzing...';
        analysisStatusEl.textContent = `Running ${selected.length} analysis step(s) on ${currentJobId}. This may take a few seconds while the trajectory loads.`;
        analysisResultsEl.innerHTML = '';

        fetch(`/api/jobs/${currentJobId}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ analyses: selected, params })
        })
            .then(r => r.json().then(data => ({ ok: r.ok, data })))
            .then(({ ok, data }) => {
                if (!ok || data.error) {
                    throw new Error(data.error || 'Analysis failed');
                }
                renderAnalysisResults(data.results || {});
                analysisStatusEl.textContent =
                    `Analysis complete (${Object.keys(data.results || {}).length} step(s)).`;
            })
            .catch(err => {
                analysisStatusEl.textContent = 'Analysis failed: ' + err.message;
            })
            .finally(() => {
                runAnalysisBtn.disabled = false;
                runAnalysisBtn.querySelector('.spinner').classList.add('hidden');
                runAnalysisBtn.querySelector('.btn-text').textContent = 'Run Analysis';
            });
    }

    function renderAnalysisResults(results) {
        analysisResultsEl.innerHTML = '';

        const order = [
            'rg', 'rmsd', 'rmsf', 'e2e', 'hbonds', 'salt_bridges',
            'shape', 'cross_corr', 'ss', 'pca', 'force_ext', 'contacts'
        ];
        const sortedKeys = Object.keys(results).sort((a, b) => {
            const ai = order.indexOf(a); const bi = order.indexOf(b);
            return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
        });

        for (const key of sortedKeys) {
            const result = results[key];
            const card = document.createElement('div');
            card.className = 'analysis-result-card';

            const title = document.createElement('h3');
            title.textContent = result.name || key;
            card.appendChild(title);

            if (result.error) {
                const err = document.createElement('div');
                err.className = 'analysis-error';
                err.textContent = result.error;
                card.appendChild(err);
                analysisResultsEl.appendChild(card);
                continue;
            }

            if (result.description) {
                const desc = document.createElement('div');
                desc.className = 'analysis-description';
                desc.textContent = result.description;
                card.appendChild(desc);
            }

            if (result.image_url) {
                const img = document.createElement('img');
                img.src = result.image_url + '?t=' + Date.now();
                img.alt = result.name || key;
                card.appendChild(img);
            }

            if (result.stats && Object.keys(result.stats).length > 0) {
                const stats = document.createElement('div');
                stats.className = 'analysis-stats';
                stats.textContent = Object.entries(result.stats)
                    .map(([k, v]) => `${k}: ${typeof v === 'number' ? v.toFixed(3) : v}`)
                    .join('\n');
                card.appendChild(stats);
            }

            analysisResultsEl.appendChild(card);
        }
    }
});
