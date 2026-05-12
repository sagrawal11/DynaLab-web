// Frontend logic for the DynaLab intermediate UI.
// Talks to the Flask backend in web/server/app.py via /api/* JSON endpoints.

document.addEventListener('DOMContentLoaded', function () {
    // ----- Element handles -----
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

    const constTempParams = document.getElementById('const-temp-params');
    const replicaParams = document.getElementById('replica-params');
    const enablePulling = document.getElementById('enable-pulling');
    const pullingContent = document.getElementById('pulling-content');
    const pullingMode = document.getElementById('pulling-mode');
    const afmSetup = document.getElementById('afm-setup');
    const tensionSetup = document.getElementById('tension-setup');
    const enableMembrane = document.getElementById('enable-membrane');
    const membraneContent = document.getElementById('membrane-content');
    const enableRestraints = document.getElementById('enable-restraints');
    const restraintsContent = document.getElementById('restraints-content');
    const wallConstText = document.getElementById('wall-const-text');
    const wallPairText = document.getElementById('wall-pair-text');
    const springConstText = document.getElementById('spring-const-text');
    const springPairText = document.getElementById('spring-pair-text');
    const nailText = document.getElementById('nail-text');
    const addAfmBtn = document.getElementById('add-afm-btn');
    const addTensionBtn = document.getElementById('add-tension-btn');

    // Sweep
    const enableSweep = document.getElementById('enable-sweep');
    const sweepContent = document.getElementById('sweep-content');
    const sweepMode = document.getElementById('sweep-mode');
    const sweepForces = document.getElementById('sweep-forces');
    const sweepReplicas = document.getElementById('sweep-replicas');
    const sweepAnchor = document.getElementById('sweep-anchor');
    const sweepPuller = document.getElementById('sweep-puller');
    const sweepResultsEl = document.getElementById('sweep-results');
    const runSweepAnalysisBtn = document.getElementById('run-sweep-analysis-btn');
    const sweepAnalysisResults = document.getElementById('sweep-analysis-results');

    // Backmap
    const backmapSection = document.getElementById('backmap-section');
    const intermediatesList = document.getElementById('intermediates-list');
    const runBackmapBtn = document.getElementById('run-backmap-btn');
    const backmapStatus = document.getElementById('backmap-status');
    const backmappedList = document.getElementById('backmapped-list');

    // Design
    const designSection = document.getElementById('design-section');
    const designIntermediate = document.getElementById('design-intermediate');
    const designHotspots = document.getElementById('design-hotspots');
    const designNDesigns = document.getElementById('design-n-designs');
    const designBinderLength = document.getElementById('design-binder-length');
    const designNSeqs = document.getElementById('design-n-seqs');
    const designUseMock = document.getElementById('design-use-mock');
    const runDesignBtn = document.getElementById('run-design-btn');
    const designStatus = document.getElementById('design-status');
    const designResults = document.getElementById('design-results');

    // Experimental
    const experimentalSection = document.getElementById('experimental-section');
    const expZones = document.getElementById('exp-zones');
    const expForceLow = document.getElementById('exp-force-low');
    const expForceHigh = document.getElementById('exp-force-high');
    const expThresholds = document.getElementById('exp-thresholds');
    const expAttachment = document.getElementById('exp-attachment');
    const makeDesignSheetBtn = document.getElementById('make-design-sheet-btn');
    const expDesignStatus = document.getElementById('exp-design-status');
    const expDesignOutput = document.getElementById('exp-design-output');
    const wetlabCsv = document.getElementById('wetlab-csv');
    const wetlabUploadStatus = document.getElementById('wetlab-upload-status');
    const wetlabPredThreshold = document.getElementById('wetlab-pred-threshold');
    const runComparisonBtn = document.getElementById('run-comparison-btn');
    const comparisonStatus = document.getElementById('comparison-status');
    const comparisonResults = document.getElementById('comparison-results');

    // Settings
    const openSettingsBtn = document.getElementById('open-settings-btn');
    const settingsDialog = document.getElementById('settings-dialog');
    const settingsCloseBtn = document.getElementById('settings-close-btn');
    const settingsSaveBtn = document.getElementById('settings-save-btn');
    const tamarindApiKey = document.getElementById('tamarind-api-key');
    const tamarindEndpoint = document.getElementById('tamarind-endpoint');
    const settingsStatus = document.getElementById('settings-status');

    const helpModal = document.getElementById('help-modal');
    const helpModalTitle = document.getElementById('help-modal-title');
    const helpModalBody = document.getElementById('help-modal-body');
    const helpModalClose = document.getElementById('help-modal-close');
    let helpModalListenersBound = false;

    /**
     * Rich help copy lives in help-content.js as window.DYNALAB_HELP_CONTENT
     * (overviewHtml + optional detailHtml). Fallback below if that script fails to load.
     */
    const HELP_CONTENT = window.DYNALAB_HELP_CONTENT || {
        upload_pdb: {
            title: 'Structure upload',
            overviewHtml: '<p>Help content failed to load. Refresh the page or ensure <code>help-content.js</code> is served next to <code>script.js</code>.</p>',
            detailHtml: '',
        },
    };

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function buildHelpModalBody(overviewHtml, detailHtml) {
        const hasDetail = Boolean(detailHtml && String(detailHtml).trim());
        const detailBlock = hasDetail
            ? '<div class="help-modal__actions">' +
                '<button type="button" class="help-modal__more-toggle" aria-expanded="false" aria-controls="help-modal-detail-region">Give me more info</button>' +
                '</div>' +
                '<div id="help-modal-detail-region" class="help-modal__detail help-modal__detail--rich hidden" role="region" hidden>' +
                '<h3 class="help-modal__detail-heading">Plain-language deep dive</h3>' +
                '<div class="help-modal__detail-prose">' +
                detailHtml +
                '</div></div>'
            : '';
        return '<div class="help-modal__overview">' + overviewHtml + '</div>' + detailBlock;
    }

    function openHelpForKey(key) {
        if (!helpModal || !key) return;
        const raw = HELP_CONTENT[key];
        const entry = raw && (raw.overviewHtml != null || raw.html != null)
            ? raw
            : {
                title: 'Help',
                overviewHtml: `<p>There is no description for this topic yet. Reference key: <code>${escapeHtml(key)}</code>.</p>`,
                detailHtml: '',
            };
        const title = entry.title || 'Help';
        const overview = entry.overviewHtml ?? entry.html ?? '';
        const detail = entry.detailHtml ?? '';
        if (helpModalTitle) helpModalTitle.textContent = title;
        if (helpModalBody) helpModalBody.innerHTML = buildHelpModalBody(overview, detail);
        helpModal.classList.remove('hidden');
        helpModal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        requestAnimationFrame(() => {
            if (helpModalClose) helpModalClose.focus();
        });
    }

    let selectedFile = null;
    let currentJobId = null;
    let currentSweepId = null;
    let lastWetlabFilename = null;
    let currentConfig = {};
    /** While a job is polling, config summary shows this snapshot (submitted settings). */
    let configSummaryFrozen = false;
    let frozenConfigSummaryText = '';

    const modeDescriptions = {
        constant: 'Standard molecular dynamics at constant temperature.',
        replica:  'Replica exchange MD for enhanced sampling across temperature range.',
    };

    init();

    // -------------------------------------------------------------------
    // Initialisation
    // -------------------------------------------------------------------
    function init() {
    updateSliderValues();
    updateConfigSummary();
    updateCardVisibility();
    setupEventListeners();
        loadSettingsStatus();
        setupHelpModal();
    }

    function setupEventListeners() {
        pdbFileInput.addEventListener('change', handleFileUpload);
        userName.addEventListener('input', updateConfigSummary);
        userEmail.addEventListener('input', updateConfigSummary);
        userName.addEventListener('input', updateRunButton);
        userEmail.addEventListener('input', updateRunButton);

        simMode.addEventListener('change', () => {
            modeDescription.textContent = modeDescriptions[simMode.value];
            updateCardVisibility();
            updateConfigSummary();
        });

        [duration, frameInterval, temperature, nReplicas, tempLow, tempHigh,
            replicaInterval, membraneInner, membraneOuter].forEach(slider => {
                slider.addEventListener('input', () => {
                updateSliderValues();
                updateConfigSummary();
            });
        });

        const basicIr = document.getElementById('basic-independent-replicas');
        if (basicIr) {
            ['input', 'change'].forEach(ev => basicIr.addEventListener(ev, updateConfigSummary));
        }

        membraneCoordSystem.addEventListener('change', updateConfigSummary);

        enablePulling.addEventListener('change', () => {
            toggleCardContent(pullingContent, enablePulling.checked);
            syncSweepPullingExclusivity();
            updateConfigSummary();
        });
        pullingMode.addEventListener('change', () => {
            const isVel = pullingMode.value === 'velocity';
            afmSetup.classList.toggle('hidden', !isVel);
            tensionSetup.classList.toggle('hidden', isVel);
            updateConfigSummary();
        });

        function setMembraneControlsInteractive(on) {
            [membraneCoordSystem, membraneInner, membraneOuter, disableRecentering, disableZRecentering].forEach((el) => {
                if (!el) return;
                el.disabled = !on;
                el.setAttribute('aria-disabled', on ? 'false' : 'true');
            });
        }

        enableMembrane.addEventListener('change', () => {
            toggleCardContent(membraneContent, enableMembrane.checked);
            setMembraneControlsInteractive(enableMembrane.checked);
            updateConfigSummary();
        });
        setMembraneControlsInteractive(enableMembrane.checked);
        enableRestraints.addEventListener('change', () => {
            toggleCardContent(restraintsContent, enableRestraints.checked);
            updateConfigSummary();
        });
        disableRecentering.addEventListener('change', updateConfigSummary);
        disableZRecentering.addEventListener('change', updateConfigSummary);

        [wallConstText, wallPairText, springConstText, springPairText, nailText].forEach(el => {
            if (el) el.addEventListener('input', updateConfigSummary);
        });

        ['enable-wall-const', 'enable-wall-pair', 'enable-spring-const',
            'enable-spring-pair', 'enable-nail'].forEach(checkboxId => {
                const cb = document.getElementById(checkboxId);
                if (!cb) return;
                cb.addEventListener('change', () => {
                    const entriesId = checkboxId.replace('enable-', '') + '-entries';
                    const entries = document.getElementById(entriesId);
                    if (entries) entries.classList.toggle('hidden', !cb.checked);
                updateConfigSummary();
            });
            });

        addAfmBtn.addEventListener('click', addAfmEntry);
        if (addTensionBtn) addTensionBtn.addEventListener('click', addTensionEntry);
        const addDlBtn = document.getElementById('add-distance-lock-btn');
        if (addDlBtn) addDlBtn.addEventListener('click', addDistanceLockEntry);
        const enableDl = document.getElementById('enable-distance-locks');
        const dlWrap = document.getElementById('distance-lock-entries');
        const rigidSg = document.getElementById('restraint-group-rigid-spring');
        function updateRestraintGroupSpringVisibility() {
            const rigidOn = rigidSg && rigidSg.checked;
            document.querySelectorAll('.distance-lock-k-field').forEach(el => {
                el.classList.toggle('hidden', rigidOn);
            });
        }
        if (enableDl && dlWrap && addDlBtn) {
            enableDl.addEventListener('change', () => {
                const on = enableDl.checked;
                dlWrap.classList.toggle('hidden', !on);
                addDlBtn.classList.toggle('hidden', !on);
                if (on) updateRestraintGroupSpringVisibility();
                updateConfigSummary();
            });
        }
        if (rigidSg) {
            rigidSg.addEventListener('change', () => {
                updateRestraintGroupSpringVisibility();
                updateConfigSummary();
            });
        }
        updateRestraintGroupSpringVisibility();
        setupRemoveHandlers();

        runBtn.addEventListener('click', runSimulationOrSweep);

        // Sweep
        if (enableSweep) {
            enableSweep.addEventListener('change', () => {
                toggleCardContent(sweepContent, enableSweep.checked);
                syncSweepPullingExclusivity();
                updateConfigSummary();
            });
        }
        if (runSweepAnalysisBtn) {
            runSweepAnalysisBtn.addEventListener('click', runSweepAnalysis);
        }

        if (runAnalysisBtn) runAnalysisBtn.addEventListener('click', runAnalysis);
        const pcaInput = document.getElementById('pca-n-components');
        if (pcaInput) {
            ['click', 'mousedown', 'keydown'].forEach(ev => {
                pcaInput.addEventListener(ev, e => e.stopPropagation());
            });
        }

        // Backmap
        if (runBackmapBtn) runBackmapBtn.addEventListener('click', runBackmap);

        // Design
        if (runDesignBtn) runDesignBtn.addEventListener('click', runDesignWithGuard);

        // Experimental
        if (makeDesignSheetBtn) makeDesignSheetBtn.addEventListener('click', makeExperimentSheet);
        if (wetlabCsv) wetlabCsv.addEventListener('change', uploadWetlabCsv);
        if (runComparisonBtn) runComparisonBtn.addEventListener('click', runComparison);

        // Settings
        if (openSettingsBtn) openSettingsBtn.addEventListener('click', openSettings);
        if (settingsCloseBtn) settingsCloseBtn.addEventListener('click', closeSettings);
        if (settingsSaveBtn) settingsSaveBtn.addEventListener('click', saveSettings);

        syncSweepPullingExclusivity();
    }

    // -------------------------------------------------------------------
    // File upload + sliders + config summary (existing behavior)
    // -------------------------------------------------------------------
    function handleFileUpload(e) {
        const file = e.target.files[0];
        if (!file) return;
            selectedFile = file;
        fileInfo.innerHTML =
            `<strong>Selected:</strong> ${file.name} (${(file.size / 1024).toFixed(1)} KB)` +
            `<br><strong>Type:</strong> ${file.type || 'PDB structure file'}`;
            fileInfo.classList.remove('hidden');
            updateRunButton();
    }

    function updateSliderValues() {
        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        set('duration-value', duration.value);
        set('frame-value', frameInterval.value);
        set('temp-value', temperature.value);
        set('replicas-value', nReplicas.value);
        set('temp-low-value', tempLow.value);
        set('temp-high-value', tempHigh.value);
        set('replica-interval-value', replicaInterval.value);
        set('inner-value', membraneInner.value);
        set('outer-value', membraneOuter.value);
    }

    function syncSweepPullingExclusivity() {
        if (!enableSweep || !enablePulling) return;
        const isRep = simMode && simMode.value === 'replica';
        if (isRep) return;
        if (enableSweep.checked) {
            enableSweep.disabled = false;
            enablePulling.disabled = true;
            if (enablePulling.checked) {
                enablePulling.checked = false;
                toggleCardContent(pullingContent, false);
            }
        } else if (enablePulling.checked) {
            enableSweep.disabled = true;
            enablePulling.disabled = false;
        } else {
            enableSweep.disabled = false;
            enablePulling.disabled = false;
        }
    }

    function updateCardVisibility() {
        const isReplica = simMode.value === 'replica';
        constTempParams.classList.toggle('hidden', isReplica);
        replicaParams.classList.toggle('hidden', !isReplica);
        if (enablePulling) {
            enablePulling.disabled = isReplica;
            if (isReplica && enablePulling.checked) {
                enablePulling.checked = false;
                toggleCardContent(pullingContent, false);
            }
        }
        if (enableSweep) {
            enableSweep.disabled = isReplica;
            if (isReplica && enableSweep.checked) {
                enableSweep.checked = false;
                if (sweepContent) toggleCardContent(sweepContent, false);
            }
        }
        syncSweepPullingExclusivity();
    }

    function toggleCardContent(content, enabled) {
        content.classList.toggle('disabled', !enabled);
    }

    function addAfmEntry() {
        const afmEntries = document.getElementById('afm-entries');
        const idx = afmEntries.children.length + 1;
        const entry = document.createElement('div');
        entry.className = 'afm-entry';
        entry.innerHTML =
            `<div class="afm-entry-header"><h4>AFM Point ${idx}</h4></div>
            <div class="afm-content">
                <div class="afm-row">
                    <div class="afm-field">
                        <label>Residue</label>
                        <input type="number" class="afm-residue" min="0" value="0">
                    </div>
                    <div class="afm-field">
                        <label>Spring Constant</label>
                        <input type="number" class="afm-spring" step="0.01" value="0.05">
                    </div>
                </div>
                <div class="afm-row">
                    <div class="afm-field">
                        <label>Tip Position (x,y,z)</label>
                        <div class="xyz-compact">
                            <input type="number" class="afm-tip-x" step="0.1" value="0">
                            <input type="number" class="afm-tip-y" step="0.1" value="0">
                            <input type="number" class="afm-tip-z" step="0.1" value="0">
                        </div>
                    </div>
                    <div class="afm-field">
                        <label>Pulling Velocity (x,y,z)</label>
                        <div class="xyz-compact">
                            <input type="number" class="afm-vel-x" step="0.001" value="0">
                            <input type="number" class="afm-vel-y" step="0.001" value="0">
                            <input type="number" class="afm-vel-z" step="0.001" value="-0.001">
                        </div>
                    </div>
                </div>
                <button type="button" class="remove-afm-btn">Remove</button>
            </div>`;
        afmEntries.appendChild(entry);
        setupRemoveHandlers();
        updateConfigSummary();
    }

    function addTensionEntry() {
        const entries = document.getElementById('tension-entries');
        const idx = entries.children.length + 1;
        const entry = document.createElement('div');
        entry.className = 'afm-entry';
        entry.innerHTML =
            `<div class="afm-entry-header"><h4>Tension Point ${idx}</h4></div>
            <div class="afm-content">
                <div class="afm-row">
                    <div class="afm-field">
                        <label>Residue</label>
                        <input type="number" class="tension-residue" min="0" value="0">
            </div>
                    <div class="afm-field">
                        <label>Tension (tx, ty, tz) - kT/A</label>
                        <div class="xyz-compact">
                            <input type="number" class="tension-tx" step="0.01" value="0">
                            <input type="number" class="tension-ty" step="0.01" value="0">
                            <input type="number" class="tension-tz" step="0.01" value="0.5">
                        </div>
                    </div>
                </div>
                <button type="button" class="remove-tension-btn">Remove</button>
            </div>`;
        entries.appendChild(entry);
        setupRemoveHandlers();
        updateConfigSummary();
    }

    function addDistanceLockEntry() {
        const entries = document.getElementById('distance-lock-entries');
        if (!entries) return;
        const idx = entries.querySelectorAll('.afm-entry').length + 1;
        const entry = document.createElement('div');
        entry.className = 'afm-entry';
        entry.innerHTML =
            `<div class="afm-entry-header"><h4>Pair ${idx}</h4></div>
            <div class="afm-content">
                <div class="afm-row">
                    <div class="afm-field">
                        <label>Residue A</label>
                        <input type="number" class="distance-lock-res1" min="0" value="0">
                    </div>
                    <div class="afm-field">
                        <label>Residue B</label>
                        <input type="number" class="distance-lock-res2" min="0" value="1">
                    </div>
                    <div class="afm-field">
                        <label>Target distance (Å)</label>
                        <input type="number" class="distance-lock-r0" step="0.01" value="" placeholder="from PDB">
                    </div>
                    <div class="afm-field distance-lock-k-field hidden">
                        <label>Spring const (advanced)</label>
                        <input type="number" class="distance-lock-k" step="0.1" value="4">
                    </div>
                </div>
                <button type="button" class="remove-distance-lock-btn">Remove pair</button>
            </div>`;
        entries.appendChild(entry);
        setupRemoveHandlers();
        const rigidSg = document.getElementById('restraint-group-rigid-spring');
        if (rigidSg) {
            document.querySelectorAll('.distance-lock-k-field').forEach(el => {
                el.classList.toggle('hidden', rigidSg.checked);
            });
        }
        updateConfigSummary();
    }

    function setupRemoveHandlers() {
        document.querySelectorAll('.remove-afm-btn').forEach(btn => {
            btn.onclick = () => { btn.closest('.afm-entry').remove(); updateConfigSummary(); };
            });
        document.querySelectorAll('.remove-tension-btn').forEach(btn => {
            btn.onclick = () => { btn.closest('.afm-entry').remove(); updateConfigSummary(); };
        });
        document.querySelectorAll('.remove-distance-lock-btn').forEach(btn => {
            btn.onclick = () => { btn.closest('.afm-entry').remove(); updateConfigSummary(); };
        });
        document.querySelectorAll('.afm-entry input').forEach(input => {
            input.removeEventListener('input', updateConfigSummary);
            input.addEventListener('input', updateConfigSummary);
        });
    }

    function buildConfigSummaryText() {
        const durationVal = parseInt(duration.value, 10);
        const frameVal = parseInt(frameInterval.value, 10);
        const tempVal = parseFloat(temperature.value);
        const sweepOn = enableSweep ? enableSweep.checked : false;
        let summary = `Contact: ${userName.value || 'Not specified'} (${userEmail.value || 'Not specified'})\n` +
            `Sim mode: ${simMode.options[simMode.selectedIndex].text}\n` +
            `Duration: ${durationVal} steps (~${(durationVal * 0.05).toFixed(1)} ns)\n` +
            `Frame Interval: ${frameVal} steps\n` +
            `Temperature: ${tempVal}\n` +
            `Force field: ff_2.1`;
        if (simMode && simMode.value === 'constant') {
            const ir = document.getElementById('basic-independent-replicas');
            const n = ir ? parseInt(ir.value, 10) : 1;
            if (!Number.isNaN(n) && n > 1) summary += `\nIndependent replicas: ${n}`;
        } else if (simMode && simMode.value === 'replica') {
            summary += `\nReplica exchange: ${nReplicas.value} replicas, T_low=${tempLow.value}, T_high=${tempHigh.value}, interval=${replicaInterval.value}`;
        }
        if (sweepOn) {
            summary += `\nForce sweep: enabled (${(sweepForces.value || '').split(',').filter(x => x.trim()).length} forces, ${sweepReplicas.value} replicas)`;
        } else if (enablePulling.checked) {
            summary += `\nPulling: enabled (${pullingMode ? pullingMode.value : 'velocity'})`;
        }
        const er = document.getElementById('enable-restraints');
        const edl = document.getElementById('enable-distance-locks');
        if (er && er.checked && edl && edl.checked) {
            const n = readDistanceLockEntries().length;
            if (n) {
                const rig = document.getElementById('restraint-group-rigid-spring');
                const stiff = rig && rig.checked ? 'rigid bridge' : 'custom stiffness';
                summary += `\nRestraint groups: ${n} pair(s), ${stiff}`;
            }
        }
        const esp = document.getElementById('enable-spring-pair');
        if (er && er.checked && esp && esp.checked && springPairText && springPairText.value.trim()) {
            summary += '\nPair spring (manual table): enabled';
        }
        if (enableMembrane && enableMembrane.checked) {
            const mi = parseFloat(membraneInner.value);
            const mo = parseFloat(membraneOuter.value);
            const th = (Number.isFinite(mi) && Number.isFinite(mo)) ? (mo - mi) : NaN;
            summary += `\nMembrane: on (${membraneCoordSystem.value}), inner=${mi} Å, outer=${mo} Å`;
            if (Number.isFinite(th)) summary += ` → thickness ${th.toFixed(1)} Å`;
            if (disableRecentering && disableRecentering.checked) summary += ', disable recentering';
            if (disableZRecentering && disableZRecentering.checked) summary += ', disable z-recentering';
        } else {
            summary += '\nMembrane: off';
        }
        return summary;
    }

    function freezeConfigSummaryForRun() {
        frozenConfigSummaryText = buildConfigSummaryText();
        configSummaryFrozen = true;
        if (configSummary) configSummary.textContent = frozenConfigSummaryText;
    }

    function unfreezeConfigSummary() {
        configSummaryFrozen = false;
        frozenConfigSummaryText = '';
        updateConfigSummary();
    }

    function updateConfigSummary() {
        if (configSummaryFrozen) {
            if (configSummary) configSummary.textContent = frozenConfigSummaryText;
            return;
        }
        currentConfig = {
            userName:    userName.value || 'Not specified',
            userEmail:   userEmail.value || 'Not specified',
            simMode:     simMode.value,
            duration:    parseInt(duration.value, 10),
            frameInterval: parseInt(frameInterval.value, 10),
            temperature: parseFloat(temperature.value),
            enablePulling: enablePulling.checked,
            pullingMode: pullingMode ? pullingMode.value : 'velocity',
            enableSweep: enableSweep ? enableSweep.checked : false,
        };
        if (configSummary) configSummary.textContent = buildConfigSummaryText();
    }

    function updateRunButton() {
        const hasReq = selectedFile && userName.value.trim() && userEmail.value.trim();
        runBtn.disabled = !hasReq;
    }

    function canonicalPairKey(a, b) {
        const x = Math.min(Number(a), Number(b));
        const y = Math.max(Number(a), Number(b));
        return `${x}|${y}`;
    }

    /** Client-side checks mirroring web/server/app.py ``_validate_single_job_config`` (server still authoritative). */
    function validateSingleInputs() {
        const d = parseInt(duration.value, 10);
        const fi = parseInt(frameInterval.value, 10);
        if (Number.isNaN(d) || d < 1) return 'Duration must be a positive integer.';
        if (Number.isNaN(fi) || fi < 1) return 'Frame interval must be a positive integer.';

        if (enablePulling.checked) {
            const mode = pullingMode ? pullingMode.value : 'velocity';
            if (mode === 'tension') {
                const rows = readTensionEntries();
                if (!rows.length) return 'Constant-tension pulling needs at least one tension row.';
                const res = [];
                for (let i = 0; i < rows.length; i++) {
                    const r = parseInt(rows[i].residue, 10);
                    if (Number.isNaN(r) || r < 0) return `Tension row ${i + 1}: invalid residue index.`;
                    res.push(r);
                }
                if (new Set(res).size !== res.length) {
                    return 'Constant-tension pulling: use each residue at most once across tension rows.';
                }
            } else {
                const rows = readAfmEntries();
                if (!rows.length) return 'Velocity-clamp pulling needs at least one AFM row.';
                const res = [];
                for (let i = 0; i < rows.length; i++) {
                    const r = parseInt(rows[i].residue, 10);
                    if (Number.isNaN(r) || r < 0) return `AFM row ${i + 1}: invalid residue index.`;
                    res.push(r);
                }
                if (new Set(res).size !== res.length) {
                    return 'Velocity-clamp pulling: use each residue at most once across AFM rows.';
                }
            }
        }

        const er = document.getElementById('enable-restraints');
        const edl = document.getElementById('enable-distance-locks');
        const esp = document.getElementById('enable-spring-pair');
        const locksOn = er && er.checked && edl && edl.checked;
        const manualOn = er && er.checked && esp && esp.checked && springPairText && springPairText.value.trim();
        if (locksOn && manualOn) {
            const locks = readDistanceLockEntries();
            if (locks.length) {
                return 'Cannot combine distance-lock pairs with manual pair spring text (same backend table). Disable one.';
            }
        }
        if (enableMembrane && enableMembrane.checked) {
            const mi = parseFloat(membraneInner.value);
            const mo = parseFloat(membraneOuter.value);
            if (!Number.isFinite(mi) || !Number.isFinite(mo)) {
                return 'Membrane boundaries must be numbers.';
            }
            if (mo <= mi) {
                return 'Membrane outer boundary (Å) must be greater than the inner boundary.';
            }
            const th = mo - mi;
            if (th < 4 || th > 120) {
                return 'Implied membrane thickness (outer − inner) must be between 4 and 120 Å.';
            }
        }

        if (locksOn) {
            const locks = readDistanceLockEntries();
            const seen = new Set();
            for (let i = 0; i < locks.length; i++) {
                const a = parseInt(locks[i].res1, 10);
                const b = parseInt(locks[i].res2, 10);
                if (Number.isNaN(a) || Number.isNaN(b)) continue;
                if (a === b) return `Distance lock pair ${i + 1}: the two residues must differ.`;
                const k = canonicalPairKey(a, b);
                if (seen.has(k)) {
                    return `Duplicate distance-lock pair (${Math.min(a, b)}, ${Math.max(a, b)}). Remove the duplicate.`;
                }
                seen.add(k);
            }
        }
        return null;
    }

    function validateBeforeSweep() {
        if (enablePulling && enablePulling.checked) {
            return 'Cannot run a force sweep together with single-job pulling. Disable pulling or turn off the sweep.';
        }
        return validateSingleInputs();
    }

    function appendMembraneConfig(config) {
        const em = document.getElementById('enable-membrane');
        config.membraneEnabled = !!(em && em.checked);
        if (!config.membraneEnabled) return;
        const mi = parseFloat(membraneInner && membraneInner.value);
        const mo = parseFloat(membraneOuter && membraneOuter.value);
        config.membraneInnerAngstrom = Number.isFinite(mi) ? mi : -16;
        config.membraneOuterAngstrom = Number.isFinite(mo) ? mo : 16;
        if (config.membraneOuterAngstrom <= config.membraneInnerAngstrom) {
            config.membraneOuterAngstrom = config.membraneInnerAngstrom + 4;
        }
        config.membraneCoordSystem = (membraneCoordSystem && membraneCoordSystem.value) || 'cartesian';
        config.membraneDisableRecentering = !!(disableRecentering && disableRecentering.checked);
        config.membraneDisableZRecentering = !!(disableZRecentering && disableZRecentering.checked);
    }

    // -------------------------------------------------------------------
    // Submit job (single or sweep)
    // -------------------------------------------------------------------
    function runSimulationOrSweep() {
        if (!selectedFile || !userName.value.trim() || !userEmail.value.trim()) return;
        runBtn.disabled = true;
        const spinner = runBtn.querySelector('.spinner');
        if (spinner) spinner.classList.remove('hidden');
        runBtn.querySelector('.btn-text').textContent = 'Running...';

        progressSection.classList.remove('hidden');
        resultsSection.classList.add('hidden');
        analysisSection.classList.add('hidden');
        backmapSection.classList.add('hidden');
        designSection.classList.add('hidden');
        analysisResultsEl.innerHTML = '';
        analysisStatusEl.textContent = '';
        const log = document.getElementById('log-output');
        if (log) log.textContent = '';

        let preErr = null;
        if (enableSweep && enableSweep.checked) preErr = validateBeforeSweep();
        else preErr = validateSingleInputs();
        if (preErr) {
            const pt = document.getElementById('progress-text');
            if (pt) pt.textContent = preErr;
            resetRunButton();
            return;
        }

        if (enableSweep && enableSweep.checked) {
            if (simMode && simMode.value === 'replica') {
                const pt = document.getElementById('progress-text');
                if (pt) pt.textContent = 'Force sweep is not available together with replica exchange. Turn off sweep or switch to constant temperature.';
                resetRunButton();
                return;
            }
            return submitSweep();
        }
        if (simMode && simMode.value === 'replica' && enablePulling.checked) {
            const pt = document.getElementById('progress-text');
            if (pt) pt.textContent = 'Replica exchange cannot be run with pulling enabled. Disable pulling or use constant temperature.';
            resetRunButton();
            return;
        }
        return submitSingle();
    }

    function submitSingle() {
        const clientErr = validateSingleInputs();
        if (clientErr) {
            document.getElementById('progress-text').textContent = clientErr;
            resetRunButton();
            return;
        }
        const config = {
            duration: parseInt(duration.value, 10),
            frameInterval: parseInt(frameInterval.value, 10),
            temperature: parseFloat(temperature.value),
            simulationMode: simMode ? simMode.value : 'constant',
            enablePulling: enablePulling.checked,
            pullingMode: pullingMode ? pullingMode.value : 'velocity',
        };
        if (simMode && simMode.value === 'replica') {
            let n = nReplicas ? parseInt(nReplicas.value, 10) : 8;
            if (Number.isNaN(n)) n = 8;
            config.replicaNReplicas = Math.min(32, Math.max(2, n));
            let tLo = tempLow ? parseFloat(tempLow.value) : 0.8;
            let tHi = tempHigh ? parseFloat(tempHigh.value) : 0.94;
            if (Number.isNaN(tLo)) tLo = 0.8;
            if (Number.isNaN(tHi)) tHi = 0.94;
            if (tHi < tLo) {
                const s = tLo;
                tLo = tHi;
                tHi = s;
            }
            config.replicaTLow = tLo;
            config.replicaTHigh = tHi;
            let ri = replicaInterval ? parseInt(replicaInterval.value, 10) : 10;
            if (Number.isNaN(ri)) ri = 10;
            config.replicaInterval = Math.min(10000, Math.max(1, ri));
        }
        if (config.enablePulling) {
            if (config.pullingMode === 'tension') {
                config.tensionEntries = readTensionEntries();
                const tipn = document.getElementById('tension-input-pn');
                config.tensionInPiconewtons = !!(tipn && tipn.checked);
            } else {
                config.afmEntries = readAfmEntries();
            }
        }
        const er = document.getElementById('enable-restraints');
        const edl = document.getElementById('enable-distance-locks');
        if (er && er.checked && edl && edl.checked) {
            const locks = readDistanceLockEntries();
            if (locks.length) {
                config.distanceLockPairs = locks;
                const rig = document.getElementById('restraint-group-rigid-spring');
                config.restraintGroupRigidSpring = rig ? rig.checked : true;
            }
        }
        const esp = document.getElementById('enable-spring-pair');
        if (er && er.checked && esp && esp.checked && springPairText && springPairText.value.trim()) {
            config.enablePairSpringText = true;
            config.pairSpringText = springPairText.value.trim();
        }
        if (simMode && simMode.value === 'constant') {
            const ir = document.getElementById('basic-independent-replicas');
            let n = ir ? parseInt(ir.value, 10) : 1;
            if (Number.isNaN(n)) n = 1;
            config.basicIndependentReplicas = Math.min(32, Math.max(1, n));
        }
        appendMembraneConfig(config);
        const formData = new FormData();
        formData.append('pdb', selectedFile);
        formData.append('config', JSON.stringify(config));

        fetch('/api/jobs', { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                currentSweepId = null;
                freezeConfigSummaryForRun();
                startTimer();
                pollJobStatus(data.job_id);
            })
            .catch(err => {
                document.getElementById('progress-text').textContent = 'Submission failed: ' + err.message;
                resetRunButton();
            });
    }

    function submitSweep() {
        const sweepErr = validateBeforeSweep();
        if (sweepErr) {
            document.getElementById('progress-text').textContent = sweepErr;
            resetRunButton();
            return;
        }
        const forces = (sweepForces.value || '').split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n));
        if (forces.length === 0) {
            document.getElementById('progress-text').textContent = 'Add at least one force to the sweep.';
            resetRunButton();
            return;
        }
        const config = {
            duration: parseInt(duration.value, 10),
            frameInterval: parseInt(frameInterval.value, 10),
            temperature: parseFloat(temperature.value),
            sweepMode: sweepMode.value,
            forces_pn: forces,
            n_replicas: parseInt(sweepReplicas.value, 10) || 1,
            anchorResidue: parseInt(sweepAnchor.value, 10) || 0,
            pullResidue: parseInt(sweepPuller.value, 10),
        };
        appendMembraneConfig(config);
        const formData = new FormData();
        formData.append('pdb', selectedFile);
        formData.append('config', JSON.stringify(config));
        const fill = document.getElementById('progress-fill');
        const text = document.getElementById('progress-text');
        if (fill) fill.style.width = '2%';
        if (text) text.textContent = 'Sweep queued...';
        fetch('/api/sweeps', { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                currentJobId = data.job_id;
                currentSweepId = data.sweep_id;
                freezeConfigSummaryForRun();
                startTimer();
                pollSweepStatus(data.job_id);
            })
            .catch(err => {
                if (text) text.textContent = 'Sweep submission failed: ' + err.message;
                resetRunButton();
            });
    }

    function readAfmEntries() {
        return Array.from(document.querySelectorAll('#afm-entries .afm-entry')).map(e => ({
            residue: e.querySelector('.afm-residue').value,
            spring:  e.querySelector('.afm-spring').value,
            velX:    e.querySelector('.afm-vel-x').value,
            velY:    e.querySelector('.afm-vel-y').value,
            velZ:    e.querySelector('.afm-vel-z').value,
        }));
    }

    function readTensionEntries() {
        return Array.from(document.querySelectorAll('#tension-entries .afm-entry')).map(e => ({
            residue: e.querySelector('.tension-residue').value,
            tx: e.querySelector('.tension-tx').value,
            ty: e.querySelector('.tension-ty').value,
            tz: e.querySelector('.tension-tz').value,
        }));
    }

    function readDistanceLockEntries() {
        const root = document.getElementById('distance-lock-entries');
        if (!root) return [];
        return Array.from(root.querySelectorAll('.afm-entry')).map(e => ({
            res1: e.querySelector('.distance-lock-res1').value,
            res2: e.querySelector('.distance-lock-res2').value,
            distanceAngstrom: (e.querySelector('.distance-lock-r0') || {}).value ?? '',
            springConst: (e.querySelector('.distance-lock-k') || {}).value || '4',
        })).filter(p => {
            const a = parseInt(p.res1, 10);
            const b = parseInt(p.res2, 10);
            return p.res1 !== '' && p.res2 !== '' && !Number.isNaN(a) && !Number.isNaN(b);
        });
    }

    // -------------------------------------------------------------------
    // Status polling
    // -------------------------------------------------------------------
    let _timerInterval = null;
    let _timerStart = null;
    function startTimer() {
        _timerStart = Date.now();
        const el = document.getElementById('elapsed-time');
        _timerInterval = setInterval(() => {
            const s = ((Date.now() - _timerStart) / 1000).toFixed(1);
            if (el) el.textContent = `Time: ${s}s`;
        }, 50);
    }
    function stopTimer() { if (_timerInterval) { clearInterval(_timerInterval); _timerInterval = null; } }

    function pollJobStatus(jobId) {
        currentJobId = jobId;
        const fill = document.getElementById('progress-fill');
        const text = document.getElementById('progress-text');
        const stepEl = document.getElementById('current-step');
        fetch('/api/jobs/' + jobId)
            .then(r => r.json())
            .then(data => {
                if (data.status === 'queued') {
                    text.textContent = 'Queued...';
                    fill.style.width = '2%';
                    stepEl.textContent = 'Step: 0';
                    setTimeout(() => pollJobStatus(jobId), 500);
                } else if (data.status === 'running') {
                    const pct = data.total_steps > 0
                        ? Math.min(99, Math.round((data.current_step / data.total_steps) * 100))
                        : 50;
                    fill.style.width = pct + '%';
                    text.textContent = `Running... ${pct}%`;
                    stepEl.textContent = `Step: ${data.current_step} / ${data.total_steps}`;
                    setTimeout(() => pollJobStatus(jobId), 500);
                } else if (data.status === 'completed') {
                    stopTimer();
                    fill.style.width = '100%';
                    text.textContent = 'Simulation complete!';
                    stepEl.textContent = `Step: ${data.total_steps} / ${data.total_steps}`;
                    displayResults(jobId);
                } else if (data.status === 'failed') {
                    stopTimer();
                    text.textContent = `Failed${data.returncode != null ? ' (exit ' + data.returncode + ')' : ''}: ${data.error || 'check server log'}`;
                    fill.style.width = '100%';
                    resetRunButton();
                }
            })
            .catch(err => {
                text.textContent = 'Status check failed: ' + err.message;
                resetRunButton();
            });
    }

    function pollSweepStatus(jobId) {
        const fill = document.getElementById('progress-fill');
        const text = document.getElementById('progress-text');
        const stepEl = document.getElementById('current-step');
        fetch('/api/sweeps/' + jobId)
            .then(r => r.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                const pct = data.progress_pct || 0;
                if (fill) fill.style.width = `${Math.min(100, pct)}%`;
                if (text) {
                    text.textContent =
                        `Sweep: ${data.completed || 0} / ${data.total || 0} sub-jobs (${pct.toFixed(1)}%)`;
                }
                if (stepEl) stepEl.textContent = 'Mode: force sweep';
                if (data.status === 'completed' || data.status === 'failed') {
                    stopTimer();
                    if (fill) fill.style.width = '100%';
                    if (text) {
                        text.textContent = data.status === 'completed'
                            ? `Sweep complete: ${data.completed} / ${data.total} sub-jobs.`
                            : `Sweep failed: ${data.error || 'see logs'}`;
                    }
                    displaySweepResults(jobId, data);
                } else {
                    setTimeout(() => pollSweepStatus(jobId), 1500);
                }
            })
            .catch(err => {
                if (text) text.textContent = 'Sweep status check failed: ' + err.message;
                resetRunButton();
            });
    }

    function displayResults(jobId) {
        unfreezeConfigSummary();
        currentJobId = jobId;
        currentSweepId = null;
        const spinner = runBtn.querySelector('.spinner');
        if (spinner) spinner.classList.add('hidden');
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

    function displaySweepResults(jobId, data) {
        unfreezeConfigSummary();
        currentJobId = jobId;
        sweepResultsEl.classList.remove('hidden');
        analysisSection.classList.remove('hidden');
        analysisResultsEl.innerHTML = '';
        const sweepOk = data.status === 'completed';
        analysisStatusEl.textContent = sweepOk
            ? '“Run Analysis” runs the checklist on every completed sweep sub-run (one block per force/replica); results are not averaged across forces. For sweep-wide rollups, use “Compute Epitope Candidates”.'
            : '';
        const spinner = runBtn.querySelector('.spinner');
        if (spinner) spinner.classList.add('hidden');
        runBtn.querySelector('.btn-text').textContent = 'Sweep Complete';
        setTimeout(resetRunButton, 1500);
    }

    function resetRunButton() {
        unfreezeConfigSummary();
        runBtn.disabled = false;
        const spinner = runBtn.querySelector('.spinner');
        if (spinner) spinner.classList.add('hidden');
        runBtn.querySelector('.btn-text').textContent = 'Run Simulation';
    }

    // -------------------------------------------------------------------
    // Single-traj analysis (existing) + sweep analysis (new)
    // -------------------------------------------------------------------
    function runAnalysis() {
        if (!currentJobId) return;
        const selected = Array.from(document.querySelectorAll('input[name="analysis"]:checked'))
            .map(cb => cb.value);
        if (selected.length === 0) { analysisStatusEl.textContent = 'Pick at least one analysis to run.'; return; }
        const params = {};
        if (selected.includes('pca')) {
            const n = parseInt(document.getElementById('pca-n-components').value, 10);
            if (Number.isFinite(n) && n >= 1) params.pca = { n_components: n };
        }
        const spinner = runAnalysisBtn.querySelector('.spinner');
        runAnalysisBtn.disabled = true;
        if (spinner) spinner.classList.remove('hidden');
        runAnalysisBtn.querySelector('.btn-text').textContent = 'Analyzing...';
        analysisStatusEl.textContent = `Running ${selected.length} analysis step(s)...`;
        analysisResultsEl.innerHTML = '';

        fetch(`/api/jobs/${currentJobId}/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ analyses: selected, params }),
        })
            .then(r => r.json().then(data => ({ ok: r.ok, data })))
            .then(({ ok, data }) => {
                if (!ok || data.error) throw new Error(data.error || 'Analysis failed');
                const res = data.results || {};
                renderAnalysisResults(analysisResultsEl, res);
                if (res.multi_replica && res.replicas) {
                    const n = Object.keys(res.replicas).length;
                    analysisStatusEl.textContent = `Analysis complete (${n} trajectory block(s)).`;
                } else {
                    analysisStatusEl.textContent = `Analysis complete (${Object.keys(res).length} step(s)).`;
                }
                refreshIntermediates();
                backmapSection.classList.remove('hidden');
            })
            .catch(err => { analysisStatusEl.textContent = 'Analysis failed: ' + err.message; })
            .finally(() => {
                runAnalysisBtn.disabled = false;
                if (spinner) spinner.classList.add('hidden');
                runAnalysisBtn.querySelector('.btn-text').textContent = 'Run Analysis';
            });
    }

    function runSweepAnalysis() {
        if (!currentJobId) return;
        const spinner = runSweepAnalysisBtn.querySelector('.spinner');
        runSweepAnalysisBtn.disabled = true;
        if (spinner) spinner.classList.remove('hidden');
        runSweepAnalysisBtn.querySelector('.btn-text').textContent = 'Analyzing...';
        sweepAnalysisResults.innerHTML = '';

        fetch(`/api/jobs/${currentJobId}/analyze-sweep`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ analyses: ['epitope_candidates', 'burial_sweep', 'intermediates'] }),
        })
            .then(r => r.json().then(data => ({ ok: r.ok, data })))
            .then(({ ok, data }) => {
                if (!ok || data.error) throw new Error(data.error || 'Sweep analysis failed');
                renderAnalysisResults(sweepAnalysisResults, data.results || {});
                refreshIntermediates();
                backmapSection.classList.remove('hidden');
                experimentalSection.classList.remove('hidden');
            })
            .catch(err => {
                const div = document.createElement('div');
                div.className = 'analysis-error';
                div.textContent = 'Sweep analysis failed: ' + err.message;
                sweepAnalysisResults.appendChild(div);
            })
            .finally(() => {
                runSweepAnalysisBtn.disabled = false;
                if (spinner) spinner.classList.add('hidden');
                runSweepAnalysisBtn.querySelector('.btn-text').textContent = 'Compute Epitope Candidates';
            });
    }

    /**
     * Human-readable title for a multi-trajectory row (force sweep folder or replica label).
     */
    function formatMultiReplicaDropdownTitle(label, ensembleKind) {
        if (ensembleKind === 'force_sweep') {
            const m = /^F_([\d.]+)pN_rep_(\d+)$/i.exec(label);
            if (m) {
                const pn = parseFloat(m[1]);
                const repIdx = parseInt(m[2], 10);
                const repHuman = repIdx + 1;
                let pnStr;
                if (Number.isFinite(pn)) {
                    pnStr = Math.abs(pn % 1) < 1e-6 ? String(Math.round(pn)) : String(pn);
                } else {
                    pnStr = m[1];
                }
                return `${pnStr} pN · replica ${repHuman}`;
            }
        }
        if (ensembleKind === 'replica_exchange') {
            return `Temperature replica · ${label}`;
        }
        return `Replica · ${label}`;
    }

    function renderAnalysisResults(target, results) {
        target.innerHTML = '';
        if (results.multi_replica && results.replicas) {
            const kind = results.ensemble_kind || 'independent';
            const isForceSweep = kind === 'force_sweep';
            const intro = document.createElement('p');
            intro.className = 'param-description';
            if (isForceSweep) {
                intro.textContent = 'Force sweep: open a row for that force and replica. Per-trajectory plots are inside each row. Cross-replica means (when present) are under “All replicas”. Sweep-wide rollups (epitopes, etc.) use “Compute Epitope Candidates” on the sweep card.';
            } else if (kind === 'replica_exchange') {
                intro.textContent = 'Replica-exchange: one expandable row per temperature replica. “All replicas” holds arithmetic means of numeric stats across the ladder (plots are not averaged).';
            } else {
                intro.textContent = 'Multiple replicas: one expandable row per trajectory. “All replicas” holds arithmetic means of numeric stats across replicas (plots are not averaged).';
            }
            target.appendChild(intro);

            const agg = results.aggregate;
            const hasAgg = agg && typeof agg === 'object' && Object.keys(agg).length > 0;

            const labelsRaw = results.replica_labels || Object.keys(results.replicas);
            const labels = kind === 'force_sweep'
                ? [...labelsRaw].sort((a, b) => {
                    const ma = /^F_([\d.]+)pN_rep_(\d+)$/i.exec(a);
                    const mb = /^F_([\d.]+)pN_rep_(\d+)$/i.exec(b);
                    if (ma && mb) {
                        const fa = parseFloat(ma[1]);
                        const fb = parseFloat(mb[1]);
                        if (fa !== fb) return fa - fb;
                        return parseInt(ma[2], 10) - parseInt(mb[2], 10);
                    }
                    return String(a).localeCompare(String(b));
                })
                : [...labelsRaw].sort();
            for (const label of labels) {
                const details = document.createElement('details');
                details.className = 'analysis-replica-details';
                const summary = document.createElement('summary');
                summary.className = 'analysis-replica-summary';
                const primary = formatMultiReplicaDropdownTitle(label, kind);
                summary.textContent = `${primary} (${label})`;
                details.appendChild(summary);
                const body = document.createElement('div');
                body.className = 'analysis-replica-details-body analysis-replica-inner';
                renderAnalysisResults(body, results.replicas[label] || {});
                details.appendChild(body);
                target.appendChild(details);
            }

            if (hasAgg) {
                const allDetails = document.createElement('details');
                allDetails.className = 'analysis-replica-details analysis-all-replicas';
                allDetails.open = true;
                const allSum = document.createElement('summary');
                allSum.className = 'analysis-replica-summary';
                const allTitle = kind === 'force_sweep'
                    ? 'All replicas — cross-run summary (scalar means only)'
                    : 'All replicas — ensemble mean (scalar stats only)';
                allSum.textContent = allTitle;
                allDetails.appendChild(allSum);
                const allBody = document.createElement('div');
                allBody.className = 'analysis-replica-details-body analysis-replica-inner';
                renderAnalysisResults(allBody, agg);
                allDetails.appendChild(allBody);
                target.appendChild(allDetails);
            }
            return;
        }

        const order = [
            'rg', 'rmsd', 'rmsf', 'e2e', 'hbonds', 'salt_bridges',
            'shape', 'cross_corr', 'ss', 'pca', 'force_ext', 'contacts',
            'burial_scan', 'dihedral', 'intermediates',
            'epitope_candidates', 'burial_sweep',
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
                target.appendChild(card);
                continue;
            }
            if (result.description) {
                const d = document.createElement('div');
                d.className = 'analysis-description';
                d.textContent = result.description;
                card.appendChild(d);
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
                    .map(([k, v]) => {
                        if (Array.isArray(v) || (v && typeof v === 'object')) {
                            return `${k}: ${JSON.stringify(v)}`;
                        }
                        return `${k}: ${typeof v === 'number' ? v.toFixed(3) : v}`;
                    })
                    .join('\n');
                card.appendChild(stats);
            }
            target.appendChild(card);
        }
    }

    // -------------------------------------------------------------------
    // Phase 2: back-mapping
    // -------------------------------------------------------------------
    function refreshIntermediates() {
        if (!currentJobId) return;
        fetch(`/api/jobs/${currentJobId}/intermediates`)
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    intermediatesList.textContent = 'Could not list intermediates: ' + data.error;
                    return;
                }
                if (!data.files || data.files.length === 0) {
                    intermediatesList.textContent = 'No intermediates yet. Run the Intermediate Clustering analysis first.';
                    return;
                }
                intermediatesList.innerHTML = `<strong>${data.files.length} intermediates:</strong> ${data.files.join(', ')}`;
                designSection.classList.remove('hidden');
                refreshDesignChoices();
            })
            .catch(err => { intermediatesList.textContent = 'Listing failed: ' + err.message; });
    }

    function runBackmap() {
        if (!currentJobId) return;
        const spinner = runBackmapBtn.querySelector('.spinner');
        runBackmapBtn.disabled = true;
        if (spinner) spinner.classList.remove('hidden');
        backmapStatus.textContent = 'Submitting back-map job...';
        fetch(`/api/jobs/${currentJobId}/backmap`, { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                backmapStatus.textContent = 'Back-mapping running...';
                pollBackmap();
            })
            .catch(err => {
                backmapStatus.textContent = 'Back-map failed: ' + err.message;
                runBackmapBtn.disabled = false;
                if (spinner) spinner.classList.add('hidden');
            });
    }

    function pollBackmap() {
        fetch('/api/jobs/' + currentJobId)
            .then(r => r.json())
            .then(data => {
                if (data.backmap_status === 'completed' || data.backmap_status === 'empty' || data.backmap_status === 'failed') {
                    runBackmapBtn.disabled = false;
                    const spinner = runBackmapBtn.querySelector('.spinner');
                    if (spinner) spinner.classList.add('hidden');
                    backmapStatus.textContent = `Back-map ${data.backmap_status}` +
                        (data.backmap_error ? `: ${data.backmap_error}` : '');
                    listBackmapped();
                    refreshDesignChoices();
            } else {
                    setTimeout(pollBackmap, 1500);
                }
            });
    }

    function listBackmapped() {
        fetch(`/api/jobs/${currentJobId}/backmapped`)
            .then(r => r.json())
            .then(data => {
                if (data.error) { backmappedList.textContent = data.error; return; }
                if (!data.files || data.files.length === 0) {
                    backmappedList.textContent = 'No back-mapped structures yet.';
                return;
            }
                const links = data.files.map(f =>
                    `<a href="/api/jobs/${currentJobId}/backmapped/${encodeURIComponent(f)}" target="_blank">${f}</a>`,
                ).join(', ');
                backmappedList.innerHTML = `<strong>Back-mapped:</strong> ${links}`;
            });
    }

    // -------------------------------------------------------------------
    // Phase 3: AI design
    // -------------------------------------------------------------------
    function refreshDesignChoices() {
        fetch(`/api/jobs/${currentJobId}/backmapped`)
            .then(r => r.json())
            .then(data => {
                designIntermediate.innerHTML = '';
                (data.files || []).forEach(f => {
                    const opt = document.createElement('option');
                    opt.value = f.replace(/\.pdb$/, '');
                    opt.textContent = f;
                    designIntermediate.appendChild(opt);
                });
                if ((data.files || []).length > 0) {
                    designSection.classList.remove('hidden');
                }
            });
    }

    function runDesignWithGuard() {
        const n = parseInt(designNDesigns.value, 10) || 0;
        if (n > 100) {
            const ok = confirm(
                `You're about to submit ${n} design backbones. ` +
                `Real-API runs are billed per design and a run of this size can be expensive. ` +
                `Proceed?`,
            );
            if (!ok) return;
        }
        runDesign();
    }

    function runDesign() {
        const body = {
            intermediate_state: designIntermediate.value,
            hotspots: (designHotspots.value || '').split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n)),
            n_designs: parseInt(designNDesigns.value, 10) || 50,
            binder_length: parseInt(designBinderLength.value, 10) || 100,
            n_seqs_per_design: parseInt(designNSeqs.value, 10) || 8,
            use_mock: designUseMock.checked,
        };
        const spinner = runDesignBtn.querySelector('.spinner');
        runDesignBtn.disabled = true;
        if (spinner) spinner.classList.remove('hidden');
        designStatus.textContent = 'Submitting design pipeline...';
        designResults.innerHTML = '';

        fetch(`/api/jobs/${currentJobId}/design`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
            .then(r => r.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                designStatus.textContent = `Design ${data.design_id} queued. Polling...`;
                pollDesign(data.design_id);
            })
            .catch(err => {
                designStatus.textContent = 'Design submission failed: ' + err.message;
                runDesignBtn.disabled = false;
                if (spinner) spinner.classList.add('hidden');
            });
    }

    function pollDesign(designId) {
        fetch(`/api/design/${currentJobId}/${designId}`)
            .then(r => r.json())
            .then(data => {
                if (data.status === 'completed') {
                    runDesignBtn.disabled = false;
                    const spinner = runDesignBtn.querySelector('.spinner');
                    if (spinner) spinner.classList.add('hidden');
                    renderDesign(designId, data);
                } else if (data.status === 'failed') {
                    runDesignBtn.disabled = false;
                    const spinner = runDesignBtn.querySelector('.spinner');
                    if (spinner) spinner.classList.add('hidden');
                    designStatus.textContent = 'Design failed: ' + (data.error || 'see logs');
                } else {
                    designStatus.textContent = `Design ${designId} ${data.status || 'running'}...`;
                    setTimeout(() => pollDesign(designId), 2000);
                }
            });
    }

    function renderDesign(designId, data) {
        designStatus.textContent = `Design ${designId} complete (${(data.results || {}).client_kind || 'unknown'} client).`;
        designResults.innerHTML = '';
        const candidates = (data.results || {}).candidates || [];
        candidates.forEach(c => {
            const card = document.createElement('div');
            card.className = 'analysis-result-card';
            const h = document.createElement('h3');
            h.textContent = `Rank ${c.rank}: ipTM ${(c.iptm || 0).toFixed(3)}`;
            card.appendChild(h);
            const seq = document.createElement('div');
            seq.className = 'analysis-stats';
            seq.textContent = `Sequence: ${c.binder_sequence || '-'}\npLDDT: ${c.plddt_mean || '-'}`;
            card.appendChild(seq);
            const a = document.createElement('a');
            a.href = `/api/design/${currentJobId}/${designId}/candidate/${c.rank}`;
            a.textContent = 'Download PDB';
            a.target = '_blank';
            card.appendChild(a);
            designResults.appendChild(card);
        });
    }

    // -------------------------------------------------------------------
    // Phase 4: experimental design + comparison
    // -------------------------------------------------------------------
    function makeExperimentSheet() {
        if (!currentJobId) { expDesignStatus.textContent = 'Run a job first.'; return; }
        const body = {
            n_zones: parseInt(expZones.value, 10) || 10,
            target_force_range: [parseFloat(expForceLow.value), parseFloat(expForceHigh.value)],
            predicted_thresholds_pn: (expThresholds.value || '').split(',')
                .map(s => parseFloat(s.trim())).filter(n => !isNaN(n)),
            attachment: expAttachment.value,
        };
        expDesignStatus.textContent = 'Generating experiment sheet...';
        fetch(`/api/jobs/${currentJobId}/experiment-design`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
            .then(r => r.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                expDesignStatus.textContent = 'Experiment sheet generated.';
                expDesignOutput.classList.remove('hidden');
                expDesignOutput.textContent = data.markdown;
            })
            .catch(err => { expDesignStatus.textContent = 'Failed: ' + err.message; });
    }

    function uploadWetlabCsv() {
        if (!currentJobId || !wetlabCsv.files || wetlabCsv.files.length === 0) return;
        const fd = new FormData();
        fd.append('csv', wetlabCsv.files[0]);
        wetlabUploadStatus.textContent = 'Uploading...';
        fetch(`/api/jobs/${currentJobId}/experimental`, { method: 'POST', body: fd })
            .then(r => r.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                lastWetlabFilename = data.filename;
                let msg = `Uploaded ${data.filename} (${data.n_rows} rows)`;
                if (data.warnings && data.warnings.length) msg += '. ' + data.warnings.join('; ');
                wetlabUploadStatus.textContent = msg;
            })
            .catch(err => { wetlabUploadStatus.textContent = 'Upload failed: ' + err.message; });
    }

    function runComparison() {
        if (!currentJobId || !lastWetlabFilename) {
            comparisonStatus.textContent = 'Upload a wet-lab CSV first.';
            return;
        }
        const thr = parseFloat(wetlabPredThreshold.value);
        if (isNaN(thr)) { comparisonStatus.textContent = 'Enter the predicted threshold (pN).'; return; }
        comparisonStatus.textContent = 'Running comparison...';
        comparisonResults.innerHTML = '';
        fetch(`/api/jobs/${currentJobId}/comparison`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ csv: lastWetlabFilename, predicted_threshold_pn: thr }),
        })
            .then(r => r.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                comparisonStatus.textContent = 'Comparison ready.';
                renderAnalysisResults(comparisonResults, { force_binding_comparison: data });
            })
            .catch(err => { comparisonStatus.textContent = 'Comparison failed: ' + err.message; });
    }

    // -------------------------------------------------------------------
    // Context help modal (?)
    // -------------------------------------------------------------------
    function setupHelpModal() {
        if (!helpModal || helpModalListenersBound) return;
        helpModalListenersBound = true;
        /* Direct listeners: avoids delegation bugs (Text targets, capture order) */
        document.querySelectorAll('[data-help]').forEach((btn) => {
            btn.addEventListener(
                'click',
                (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    openHelpForKey(btn.getAttribute('data-help'));
                },
                true
            );
        });
        if (helpModalBody) {
            helpModalBody.addEventListener('click', onHelpModalBodyClick);
        }
        document.addEventListener('click', onHelpBackdropClick, false);
        if (helpModalClose) {
            helpModalClose.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                closeHelpModal();
            });
        }
        document.addEventListener('keydown', onHelpEscapeKey);
    }

    function onHelpEscapeKey(e) {
        if (e.key !== 'Escape' || !helpModal || helpModal.classList.contains('hidden')) return;
        closeHelpModal();
    }

    function onHelpModalBodyClick(e) {
        const btn = e.target.closest('.help-modal__more-toggle');
        if (!btn || !helpModalBody || !helpModalBody.contains(btn)) return;
        e.preventDefault();
        e.stopPropagation();
        const panel = helpModalBody.querySelector('.help-modal__detail');
        if (!panel) return;
        const expanded = btn.getAttribute('aria-expanded') === 'true';
        if (expanded) {
            panel.classList.add('hidden');
            panel.hidden = true;
            btn.setAttribute('aria-expanded', 'false');
            btn.textContent = 'Give me more info';
        } else {
            panel.classList.remove('hidden');
            panel.hidden = false;
            btn.setAttribute('aria-expanded', 'true');
            btn.textContent = 'Show less';
        }
    }

    /** Clicks on text inside <button> can yield a Text node target (no .closest). */
    function elementFromEventTarget(t) {
        if (!t) return null;
        if (t.nodeType === Node.ELEMENT_NODE) return t;
        if (t.nodeType === Node.TEXT_NODE && t.parentElement) return t.parentElement;
        return null;
    }

    function onHelpBackdropClick(e) {
        const el = elementFromEventTarget(e.target);
        if (!el || !el.closest('[data-close-help]')) return;
        if (helpModal && !helpModal.classList.contains('hidden')) {
            e.preventDefault();
            closeHelpModal();
        }
    }

    function closeHelpModal() {
        if (!helpModal) return;
        helpModal.classList.add('hidden');
        helpModal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    }

    // -------------------------------------------------------------------
    // Settings dialog
    // -------------------------------------------------------------------
    function openSettings() {
        settingsDialog.classList.remove('hidden');
        loadSettingsStatus();
    }
    function closeSettings() { settingsDialog.classList.add('hidden'); }
    function loadSettingsStatus() {
        if (!settingsStatus) return;
        fetch('/api/settings/tamarind')
            .then(r => r.json())
            .then(data => {
                settingsStatus.textContent = data.configured
                    ? `Tamarind API configured (endpoint: ${data.endpoint}).`
                    : `Tamarind API not configured. Phase 3 will use the mock client by default.`;
                if (tamarindEndpoint && !tamarindEndpoint.value) tamarindEndpoint.value = data.endpoint || '';
            })
            .catch(() => { settingsStatus.textContent = 'Could not reach the server.'; });
    }
    function saveSettings() {
        fetch('/api/settings/tamarind', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_key: tamarindApiKey.value,
                endpoint: tamarindEndpoint.value,
            }),
        })
            .then(r => r.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                settingsStatus.textContent = data.configured
                    ? 'Saved. Tamarind API configured.'
                    : 'Saved. (No API key set - mock client will be used.)';
                tamarindApiKey.value = '';
            })
            .catch(err => { settingsStatus.textContent = 'Save failed: ' + err.message; });
    }
});
