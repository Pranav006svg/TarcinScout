// --------------------------------------------------
// 1. Tab Switching Handler
// --------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const tabButtons = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");

    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");
            
            // Toggle buttons
            tabButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            
            // Toggle contents
            tabContents.forEach(c => c.classList.remove("active"));
            const activePanel = document.getElementById(targetTab);
            if (activePanel) {
                activePanel.classList.add("active");
            }
        });
    });

    // Initialize: expand all college groups on the results page by default
    const collegeCards = document.querySelectorAll(".college-group-card");
    collegeCards.forEach(card => {
        card.classList.add("active-group");
    });
});

// --------------------------------------------------
// 2. Drag & Drop / File Selection UI Helper
// --------------------------------------------------
function setupDragAndDrop(dragAreaId, fileInputId, selectedPanelId, filenameId, filesizeId, removeBtnId, errorId) {
    const dragArea = document.getElementById(dragAreaId);
    const fileInput = document.getElementById(fileInputId);
    const selectedPanel = document.getElementById(selectedPanelId);
    const filenameLabel = document.getElementById(filenameId);
    const filesizeLabel = document.getElementById(filesizeId);
    const removeBtn = document.getElementById(removeBtnId);
    const errorDiv = document.getElementById(errorId);

    if (!dragArea || !fileInput) return;

    // Trigger click on input when clicking drag area
    dragArea.addEventListener("click", () => fileInput.click());

    // Drag-over styling
    ["dragenter", "dragover"].forEach(eventName => {
        dragArea.addEventListener(eventName, (e) => {
            e.preventDefault();
            dragArea.classList.add("dragover");
        }, false);
    });

    ["dragleave", "drop"].forEach(eventName => {
        dragArea.addEventListener(eventName, (e) => {
            e.preventDefault();
            dragArea.classList.remove("dragover");
        }, false);
    });

    // Handle file drop
    dragArea.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            fileInput.files = files;
            updateFileSelectedUI(files[0]);
        }
    });

    // Handle file change
    fileInput.addEventListener("change", (e) => {
        if (fileInput.files.length > 0) {
            updateFileSelectedUI(fileInput.files[0]);
        }
    });

    // Remove file action
    removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        fileInput.value = "";
        selectedPanel.style.display = "none";
        dragArea.style.display = "flex";
        if (errorDiv) errorDiv.textContent = "";
    });

    function updateFileSelectedUI(file) {
        if (errorDiv) errorDiv.textContent = "";
        
        // Validate format
        const name = file.name.toLowerCase();
        if (!name.endsWith(".csv") && !name.endsWith(".xlsx") && !name.endsWith(".xls")) {
            if (errorDiv) errorDiv.textContent = "Please upload only Excel (.xlsx, .xls) or CSV (.csv) files.";
            fileInput.value = "";
            return;
        }

        // Show selected file container
        filenameLabel.textContent = file.name;
        
        // Format size
        const sizeKB = (file.size / 1024).toFixed(1);
        filesizeLabel.textContent = `(${sizeKB} KB)`;
        
        dragArea.style.display = "none";
        selectedPanel.style.display = "flex";
    }
}

// Initialize file uploads
document.addEventListener("DOMContentLoaded", () => {
    setupDragAndDrop(
        "bulk-drag-area", 
        "bulk-file-input", 
        "bulk-file-selected", 
        "bulk-filename", 
        "bulk-filesize", 
        "btn-remove-bulk-file",
        "bulk-form-error"
    );
    
    setupDragAndDrop(
        "refiner-drag-area", 
        "refiner-file-input", 
        "refiner-file-selected", 
        "refiner-filename", 
        "refiner-filesize", 
        "btn-remove-refiner-file",
        "refiner-form-error"
    );
});

// --------------------------------------------------
// 3. AJAX Bulk Scrape & Status Polling Logic
// --------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const bulkForm = document.getElementById("bulk-scrape-form");
    const bulkInput = document.getElementById("bulk-file-input");
    const bulkError = document.getElementById("bulk-form-error");
    
    const loadingOverlay = document.getElementById("loading-overlay");
    const loadingTitle = document.getElementById("loading-title");
    const loadingStatusText = document.getElementById("loading-status-text");
    const progressFill = document.getElementById("progress-fill");
    
    const bulkDetailsDiv = document.getElementById("bulk-progress-details");
    const bulkProgressRatio = document.getElementById("bulk-progress-ratio");
    const bulkPercentComplete = document.getElementById("bulk-percent-complete");
    const bulkLogContainer = document.getElementById("bulk-log-container");

    if (!bulkForm) return;

    bulkForm.addEventListener("submit", (e) => {
        e.preventDefault();
        
        if (!bulkInput.files || bulkInput.files.length === 0) {
            bulkError.textContent = "Please select a file to scrape.";
            return;
        }

        bulkError.textContent = "";
        
        const formData = new FormData();
        formData.append("file", bulkInput.files[0]);

        // Submit file via AJAX
        fetch("/scrape_bulk", {
            method: "POST",
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => { throw new Error(err.message || "Failed to start bulk scrape."); });
            }
            return response.json();
        })
        .then(data => {
            if (data.status === "success") {
                startPolling(data.batch_id, data.total);
            } else {
                bulkError.textContent = data.message || "Scraping start failed.";
            }
        })
        .catch(err => {
            bulkError.textContent = err.message;
        });
    });

    function startPolling(batchId, totalUrls) {
        // Show and configure overlay for bulk progress logs
        loadingTitle.textContent = "Processing Bulk Scrape Queue...";
        loadingStatusText.textContent = "Queue initialized. Scraping domains...";
        progressFill.style.width = "0%";
        
        if (bulkDetailsDiv) bulkDetailsDiv.style.display = "block";
        if (bulkProgressRatio) bulkProgressRatio.textContent = `Completed 0 of ${totalUrls} URLs`;
        if (bulkPercentComplete) bulkPercentComplete.textContent = "0%";
        if (bulkLogContainer) bulkLogContainer.innerHTML = "";
        
        loadingOverlay.classList.add("visible");
        
        let renderedColleges = new Set();
        
        const pollInterval = setInterval(() => {
            fetch(`/scrape_status/${batchId}`)
            .then(res => res.json())
            .then(batch => {
                if (batch.status === "error") {
                    clearInterval(pollInterval);
                    alert("Polling error: " + batch.message);
                    loadingOverlay.classList.remove("visible");
                    return;
                }

                // Update text statuses
                if (batch.current_college) {
                    loadingStatusText.textContent = `Scraping: ${batch.current_college}`;
                }

                const completedCount = batch.completed_colleges.length;
                const percent = Math.round((completedCount / totalUrls) * 100);
                
                progressFill.style.width = `${percent}%`;
                if (bulkProgressRatio) bulkProgressRatio.textContent = `Completed ${completedCount} of ${totalUrls} URLs`;
                if (bulkPercentComplete) bulkPercentComplete.textContent = `${percent}%`;

                // Render new log rows
                batch.completed_colleges.forEach((c) => {
                    const key = c.url + c.college_name;
                    if (!renderedColleges.has(key)) {
                        renderedColleges.add(key);
                        
                        const row = document.createElement("div");
                        row.className = `bulk-log-row ${c.status}`;
                        
                        let detailText = "";
                        if (c.status === "success") {
                            detailText = `Found ${c.count} contacts`;
                        } else if (c.status === "warning") {
                            detailText = "No contacts extracted";
                        } else {
                            detailText = c.error ? `Failed: ${c.error}` : "Crawl failed";
                        }

                        row.innerHTML = `
                            <span class="bulk-log-college" title="${c.url}">${c.college_name || c.url}</span>
                            <span class="bulk-log-status">
                                <span class="status-bullet"></span>
                                ${detailText}
                            </span>
                        `;
                        
                        bulkLogContainer.appendChild(row);
                        // Scroll log container to bottom
                        bulkLogContainer.scrollTop = bulkLogContainer.scrollHeight;
                    }
                });

                // Check if process finished
                if (batch.status === "completed") {
                    clearInterval(pollInterval);
                    loadingStatusText.textContent = "Redirecting to scraped results page...";
                    progressFill.style.width = "100%";
                    setTimeout(() => {
                        window.location.href = "/results";
                    }, 1500);
                }
            })
            .catch(err => {
                console.error("Polling error: ", err);
            });
        }, 2000);
    }
});

// Refiner form overlay handler
document.addEventListener("DOMContentLoaded", () => {
    const refinerForm = document.getElementById("refiner-form");
    const refinerInput = document.getElementById("refiner-file-input");
    const refinerError = document.getElementById("refiner-form-error");
    const loadingOverlay = document.getElementById("loading-overlay");

    if (refinerForm) {
        refinerForm.addEventListener("submit", (e) => {
            if (!refinerInput.files || refinerInput.files.length === 0) {
                e.preventDefault();
                refinerError.textContent = "Please select a file to refine.";
                return;
            }
            refinerError.textContent = "";
            loadingOverlay.classList.add("visible");
        });
    }
});

// --------------------------------------------------
// 4. Single Domain Scrape Loader Hook
// --------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const scrapeForm = document.getElementById("scrape-form");
    const retryForm = document.getElementById("retry-form");
    const loadingOverlay = document.getElementById("loading-overlay");
    const statusText = document.getElementById("loading-status-text");
    const progressFill = document.getElementById("progress-fill");
    const formError = document.getElementById("form-error");

    const statusUpdates = [
        { progress: 5, text: "Connecting to domain and validating host..." },
        { progress: 15, text: "Fetching homepage HTML content..." },
        { progress: 30, text: "Parsing homepage links and identifying relevant directories..." },
        { progress: 45, text: "Found contact page candidates. Starting queue crawl..." },
        { progress: 60, text: "Crawling page: /contact-us (polite delay active)..." },
        { progress: 75, text: "Crawling page: /administration-faculty..." },
        { progress: 85, text: "Extracting contacts using AI/Gemini (with regex fallback)..." },
        { progress: 92, text: "Formatting roles, emails, and address segments..." },
        { progress: 98, text: "Writing data to SQLite and removing duplicates..." }
    ];

    function runLoaderAnimation() {
        // Ensure bulk UI panel is hidden in case it was toggled
        const bulkDetails = document.getElementById("bulk-progress-details");
        if (bulkDetails) bulkDetails.style.display = "none";
        
        loadingOverlay.classList.add("visible");
        let currentStep = 0;
        
        const updateInterval = setInterval(() => {
            if (currentStep < statusUpdates.length) {
                const step = statusUpdates[currentStep];
                statusText.textContent = step.text;
                progressFill.style.width = `${step.progress}%`;
                currentStep++;
            } else {
                statusText.textContent = "Crawl is taking slightly longer. Completing final pages...";
                progressFill.style.width = "99%";
                clearInterval(updateInterval);
            }
        }, 2200);
    }

    function validateUrl(url) {
        if (!url) return false;
        let stripped = url.replace(/^(https?:\/\/)?(www\.)?/, "");
        return stripped.includes(".") && stripped.length > 3;
    }

    if (scrapeForm) {
        scrapeForm.addEventListener("submit", (e) => {
            const urlInput = document.getElementById("college-url").value.trim();
                             
            if (!validateUrl(urlInput)) {
                e.preventDefault();
                formError.textContent = "Please enter a valid website domain or URL.";
                return;
            }
            
            formError.textContent = "";
            runLoaderAnimation();
        });
    }

    if (retryForm) {
        retryForm.addEventListener("submit", () => {
            runLoaderAnimation();
        });
    }
});

// --------------------------------------------------
// 5. Collapsible College Groups (Results page)
// --------------------------------------------------
function toggleCollegeGroup(headerElement) {
    const card = headerElement.closest(".college-group-card");
    if (card) {
        card.classList.toggle("active-group");
    }
}

// --------------------------------------------------
// 6. Search and Filter Chips for Grouped Tables
// --------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const tableSearch = document.getElementById("table-search");
    const filterChips = document.querySelectorAll(".filter-chip");
    const typeChips = document.querySelectorAll(".type-chip");
    const groupedContainer = document.getElementById("grouped-results-container");
    const noResultsDiv = document.getElementById("no-results");

    if (groupedContainer) {
        const collegeCards = groupedContainer.querySelectorAll(".college-group-card");
        let activeRoleFilter = "All";
        let activeTypeFilter = "All";
        let searchQuery = "";

        function filterGroupedData() {
            let totalVisibleContacts = 0;

            collegeCards.forEach(card => {
                const collegeName = card.getAttribute("data-college") || "";
                const collegeType = card.getAttribute("data-college-type") || "Private";
                const rows = card.querySelectorAll("tbody tr");
                let visibleRowsInCollege = 0;
                
                const matchesType = (activeTypeFilter === "All") || (collegeType === activeTypeFilter);

                rows.forEach(row => {
                    const role = row.getAttribute("data-role") || "";
                    const rowText = row.textContent.toLowerCase();
                    
                    const matchesSearch = rowText.includes(searchQuery) || collegeName.includes(searchQuery);
                    const matchesRole = (activeRoleFilter === "All") || (role === activeRoleFilter);

                    if (matchesSearch && matchesRole && matchesType) {
                        row.style.display = "";
                        visibleRowsInCollege++;
                        totalVisibleContacts++;
                    } else {
                        row.style.display = "none";
                    }
                });

                // Update contact badge count dynamically
                const badge = card.querySelector(".badge-contacts");
                if (badge) {
                    badge.textContent = `${visibleRowsInCollege} Contacts`;
                }

                // If no contacts are visible for this college, hide the entire college panel
                if (visibleRowsInCollege === 0) {
                    card.style.display = "none";
                } else {
                    card.style.display = "block";
                }
            });

            // Toggle empty states
            if (totalVisibleContacts === 0) {
                noResultsDiv.style.display = "block";
            } else {
                noResultsDiv.style.display = "none";
            }
        }

        if (tableSearch) {
            tableSearch.addEventListener("input", (e) => {
                searchQuery = e.target.value.toLowerCase().trim();
                filterGroupedData();
            });
        }

        filterChips.forEach(chip => {
            chip.addEventListener("click", () => {
                filterChips.forEach(c => c.classList.remove("active"));
                chip.classList.add("active");
                
                activeRoleFilter = chip.getAttribute("data-role");
                filterGroupedData();
            });
        });

        typeChips.forEach(chip => {
            chip.addEventListener("click", () => {
                typeChips.forEach(c => {
                    c.classList.remove("active");
                    c.style.background = "rgba(255,255,255,0.05)";
                    c.style.borderColor = "rgba(255,255,255,0.1)";
                    c.style.color = "var(--text-primary)";
                });
                chip.classList.add("active");
                chip.style.background = "rgba(139, 92, 246, 0.2)";
                chip.style.borderColor = "rgba(139, 92, 246, 0.4)";
                chip.style.color = "#c084fc";
                
                activeTypeFilter = chip.getAttribute("data-type");
                filterGroupedData();
            });
        });
    }
});

// --------------------------------------------------
// 7. Utility: Copy to Clipboard Function
// --------------------------------------------------
function copyText(text, button) {
    if (!navigator.clipboard) {
        // Fallback for non-secure contexts
        const textarea = document.createElement("textarea");
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand("copy");
            showCopiedState(button);
        } catch (err) {
            console.error("Fallback copy failed", err);
        }
        document.body.removeChild(textarea);
        return;
    }
    
    navigator.clipboard.writeText(text)
        .then(() => {
            showCopiedState(button);
        })
        .catch(err => {
            console.error("Clipboard copy failed: ", err);
        });
}

function showCopiedState(button) {
    const icon = button.querySelector("i");
    button.classList.add("copied");
    icon.className = "fa-solid fa-circle-check";
    
    setTimeout(() => {
        button.classList.remove("copied");
        icon.className = "fa-regular fa-copy";
    }, 2000);
}

// --------------------------------------------------
// 8. Download Template File Generator
// --------------------------------------------------
function downloadUrlTemplate(event) {
    event.preventDefault();
    const csvContent = "data:text/csv;charset=utf-8,College Name,Website URL\nAnna University,https://www.annauniv.edu\nIIT Madras,https://www.iitm.ac.in\nVIT Vellore,\n,https://www.srmist.edu.in\n";
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "college_discovery_template.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// --------------------------------------------------
// 9. AI Discovery — Mode Switching
// --------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const aiModeButtons = document.querySelectorAll(".ai-mode-btn");
    const aiModePanels = document.querySelectorAll(".ai-mode-panel");

    aiModeButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetMode = btn.getAttribute("data-ai-mode");
            
            // Toggle buttons
            aiModeButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            
            // Toggle panels
            aiModePanels.forEach(p => p.classList.remove("active"));
            const targetPanel = document.getElementById(`ai-mode-${targetMode}`);
            if (targetPanel) {
                targetPanel.classList.add("active");
            }
        });
    });

    // Setup AI file upload drag and drop
    setupDragAndDrop(
        "ai-drag-area", 
        "ai-file-input", 
        "ai-file-selected", 
        "ai-filename", 
        "ai-filesize", 
        "btn-remove-ai-file",
        "ai-form-error"
    );
});

// --------------------------------------------------
// 10. AI Discovery — Region Search Handler
// --------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const btnRegionSearch = document.getElementById("btn-ai-region-search");
    
    if (btnRegionSearch) {
        btnRegionSearch.addEventListener("click", () => {
            const regionInput = document.getElementById("ai-region-input");
            const institutionType = document.getElementById("ai-institution-type");
            const directivesInput = document.getElementById("ai-region-directives");
            
            const region = regionInput.value.trim();
            if (!region) {
                alert("Please enter a state, city, or district name.");
                regionInput.focus();
                return;
            }
            
            startAIDiscovery({
                mode: "region",
                input: region,
                institution_type: institutionType.value,
                custom_directives: directivesInput ? directivesInput.value.trim() : ""
            });
        });
    }
});

// --------------------------------------------------
// 11. AI Discovery — College Names Search Handler
// --------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const btnNamesSearch = document.getElementById("btn-ai-names-search");
    
    if (btnNamesSearch) {
        btnNamesSearch.addEventListener("click", () => {
            const namesInput = document.getElementById("ai-names-input");
            const directivesInput = document.getElementById("ai-names-directives");
            const names = namesInput.value.trim();
            
            if (!names) {
                alert("Please enter at least one college name.");
                namesInput.focus();
                return;
            }
            
            startAIDiscovery({
                mode: "names",
                input: names,
                institution_type: "all",
                custom_directives: directivesInput ? directivesInput.value.trim() : ""
            });
        });
    }
});

// --------------------------------------------------
// 12. AI Discovery — File Upload Handler
// --------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const aiUploadForm = document.getElementById("ai-upload-form");
    const aiFileInput = document.getElementById("ai-file-input");
    const aiFormError = document.getElementById("ai-form-error");
    const directivesInput = document.getElementById("ai-upload-directives");
    
    if (aiUploadForm) {
        aiUploadForm.addEventListener("submit", (e) => {
            e.preventDefault();
            
            if (!aiFileInput.files || aiFileInput.files.length === 0) {
                if (aiFormError) aiFormError.textContent = "Please select a file.";
                return;
            }
            
            if (aiFormError) aiFormError.textContent = "";
            
            const formData = new FormData();
            formData.append("file", aiFileInput.files[0]);
            if (directivesInput) {
                formData.append("custom_directives", directivesInput.value.trim());
            }
            
            // Show loading overlay
            showAILoadingOverlay("Processing uploaded file...");
            
            fetch("/discover_upload", {
                method: "POST",
                body: formData
            })
            .then(res => {
                if (!res.ok) return res.json().then(err => { throw new Error(err.message); });
                return res.json();
            })
            .then(data => {
                if (data.status === "success") {
                    pollAIDiscoveryStatus(data.job_id);
                } else {
                    hideAILoadingOverlay();
                    if (aiFormError) aiFormError.textContent = data.message || "Upload failed.";
                }
            })
            .catch(err => {
                hideAILoadingOverlay();
                if (aiFormError) aiFormError.textContent = err.message;
            });
        });
    }
});

// --------------------------------------------------
// 13. AI Discovery — Core AJAX + Polling Logic
// --------------------------------------------------
function startAIDiscovery(payload) {
    showAILoadingOverlay(`Starting AI discovery (${payload.mode} mode)...`);
    
    fetch("/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
    .then(res => {
        if (!res.ok) return res.json().then(err => { throw new Error(err.message); });
        return res.json();
    })
    .then(data => {
        if (data.status === "success") {
            pollAIDiscoveryStatus(data.job_id);
        } else {
            hideAILoadingOverlay();
            alert(data.message || "Discovery failed to start.");
        }
    })
    .catch(err => {
        hideAILoadingOverlay();
        alert("Error: " + err.message);
    });
}

function showAILoadingOverlay(initialMessage) {
    const overlay = document.getElementById("loading-overlay");
    const title = document.getElementById("loading-title");
    const statusText = document.getElementById("loading-status-text");
    const progressFill = document.getElementById("progress-fill");
    const bulkDetails = document.getElementById("bulk-progress-details");
    const bulkLogContainer = document.getElementById("bulk-log-container");
    const bulkProgressRatio = document.getElementById("bulk-progress-ratio");
    const bulkPercentComplete = document.getElementById("bulk-percent-complete");
    const tipsContainer = document.getElementById("tips-container");
    
    if (title) title.textContent = "🧠 AI Discovery Engine Active";
    if (statusText) statusText.textContent = initialMessage || "Initializing...";
    if (progressFill) progressFill.style.width = "0%";
    if (bulkDetails) bulkDetails.style.display = "block";
    if (bulkLogContainer) bulkLogContainer.innerHTML = "";
    if (bulkProgressRatio) bulkProgressRatio.textContent = "Initializing...";
    if (bulkPercentComplete) bulkPercentComplete.textContent = "0%";
    if (tipsContainer) {
        tipsContainer.innerHTML = `<p class="tip-text"><i class="fa-solid fa-wand-magic-sparkles" style="color: #8b5cf6;"></i> <span>Gemini AI is extracting contacts intelligently from each college website.</span></p>`;
    }
    
    if (overlay) overlay.classList.add("visible");
}

function hideAILoadingOverlay() {
    const overlay = document.getElementById("loading-overlay");
    if (overlay) overlay.classList.remove("visible");
}

function pollAIDiscoveryStatus(jobId) {
    const statusText = document.getElementById("loading-status-text");
    const progressFill = document.getElementById("progress-fill");
    const bulkProgressRatio = document.getElementById("bulk-progress-ratio");
    const bulkPercentComplete = document.getElementById("bulk-percent-complete");
    const bulkLogContainer = document.getElementById("bulk-log-container");
    
    let renderedItems = new Set();
    
    const pollInterval = setInterval(() => {
        fetch(`/discover_status/${jobId}`)
        .then(res => res.json())
        .then(job => {
            if (job.status === "error" && job.message === "Job not found.") {
                clearInterval(pollInterval);
                hideAILoadingOverlay();
                alert("Discovery job not found.");
                return;
            }
            
            // Update status text
            if (statusText && job.phase_label) {
                statusText.textContent = job.phase_label;
            }
            if (statusText && job.current_item) {
                statusText.textContent = job.current_item;
            }
            
            // Update progress
            const total = job.total || 1;
            const completed = (job.completed_colleges || []).length;
            const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
            
            if (progressFill) progressFill.style.width = `${percent}%`;
            if (bulkProgressRatio) {
                if (job.phase === "discovery") {
                    bulkProgressRatio.textContent = `Discovering colleges... Found ${job.discovered_count || 0} so far`;
                } else {
                    bulkProgressRatio.textContent = `Extracted ${completed} of ${total} colleges`;
                }
            }
            if (bulkPercentComplete) bulkPercentComplete.textContent = `${percent}%`;
            
            // Render log entries
            (job.completed_colleges || []).forEach(c => {
                const key = (c.url || "") + (c.college_name || "");
                if (!renderedItems.has(key)) {
                    renderedItems.add(key);
                    
                    const row = document.createElement("div");
                    row.className = `bulk-log-row ${c.status}`;
                    
                    let statusIcon = "";
                    let detailText = "";
                    if (c.status === "success") {
                        statusIcon = "✅";
                        detailText = `Found ${c.count} contacts`;
                    } else if (c.status === "warning") {
                        statusIcon = "⚠️";
                        detailText = "No contacts found";
                    } else if (c.status === "not_found") {
                        statusIcon = "🔍";
                        detailText = "Website not found";
                    } else {
                        statusIcon = "❌";
                        detailText = c.error || "Failed";
                    }
                    
                    row.innerHTML = `
                        <span class="bulk-log-college" title="${c.url || ''}">${statusIcon} ${c.college_name || c.url || 'Unknown'}</span>
                        <span class="bulk-log-status">
                            <span class="status-bullet"></span>
                            ${detailText}
                        </span>
                    `;
                    
                    if (bulkLogContainer) {
                        bulkLogContainer.appendChild(row);
                        bulkLogContainer.scrollTop = bulkLogContainer.scrollHeight;
                    }
                }
            });
            
            // Check if completed
            if (job.status === "completed") {
                clearInterval(pollInterval);
                
                const summary = job.summary || {};
                if (statusText) {
                    statusText.textContent = `✨ Discovery complete! Found ${summary.total_contacts || 0} contacts from ${summary.successful || 0} colleges.`;
                }
                if (progressFill) progressFill.style.width = "100%";
                
                setTimeout(() => {
                    window.location.href = "/results";
                }, 2500);
            }
            
            // Check for error
            if (job.status === "error" && job.error) {
                clearInterval(pollInterval);
                hideAILoadingOverlay();
                alert("Discovery error: " + job.error);
            }
        })
        .catch(err => {
            console.error("AI Discovery polling error:", err);
        });
    }, 2500);
}

// --------------------------------------------------
// 12. Deleting specific contacts and colleges
// --------------------------------------------------
function deleteContactRow(contactId, button) {
    if (!confirm("Are you sure you want to delete this contact?")) {
        return;
    }
    
    const row = button.closest("tr");
    const table = row.closest("table");
    const collegeCard = row.closest(".college-group-card");
    const contactsBadge = collegeCard.querySelector(".badge-contacts");
    
    fetch(`/delete_contact/${contactId}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === "success") {
            row.style.transition = "opacity 0.4s ease, transform 0.4s ease";
            row.style.opacity = "0";
            row.style.transform = "translateX(-20px)";
            
            setTimeout(() => {
                row.remove();
                
                const remainingRows = table.querySelectorAll("tbody tr");
                if (contactsBadge) {
                    contactsBadge.textContent = `${remainingRows.length} Contacts`;
                }
                
                if (remainingRows.length === 0) {
                    collegeCard.style.transition = "opacity 0.4s ease, transform 0.4s ease";
                    collegeCard.style.opacity = "0";
                    collegeCard.style.transform = "scale(0.95)";
                    setTimeout(() => {
                        collegeCard.remove();
                        checkEmptyDatabaseState();
                    }, 400);
                } else {
                    updateTotalStatsCount(-1);
                }
            }, 400);
        } else {
            alert("Error deleting contact: " + data.message);
        }
    })
    .catch(err => {
        console.error("Delete contact error:", err);
        alert("An error occurred while deleting the contact.");
    });
}

function deleteCollegeGroup(collegeName, button) {
    if (!confirm(`Are you sure you want to delete all contacts for "${collegeName}"?`)) {
        return;
    }
    
    const collegeCard = button.closest(".college-group-card");
    const contactsCount = parseInt(collegeCard.querySelector(".badge-contacts").textContent) || 0;
    
    fetch("/delete_college", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ college_name: collegeName })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === "success") {
            collegeCard.style.transition = "opacity 0.4s ease, transform 0.4s ease";
            collegeCard.style.opacity = "0";
            collegeCard.style.transform = "scale(0.95)";
            
            setTimeout(() => {
                collegeCard.remove();
                updateTotalStatsCount(-contactsCount);
                checkEmptyDatabaseState();
            }, 400);
        } else {
            alert("Error deleting college: " + data.message);
        }
    })
    .catch(err => {
        console.error("Delete college error:", err);
        alert("An error occurred while deleting the college.");
    });
}

function updateTotalStatsCount(change) {
    const totalContactsEl = document.querySelector(".stat-card:first-child .stat-num");
    if (totalContactsEl) {
        const currentCount = parseInt(totalContactsEl.textContent) || 0;
        totalContactsEl.textContent = Math.max(0, currentCount + change);
    }
}

function checkEmptyDatabaseState() {
    const container = document.getElementById("grouped-results-container");
    if (container && container.querySelectorAll(".college-group-card").length === 0) {
        window.location.reload();
    }
}

// --------------------------------------------------
// Theme Toggle Handler
// --------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const themeToggle = document.getElementById("theme-toggle");
    const themeIcon = document.getElementById("theme-toggle-icon");
    
    if (!themeToggle || !themeIcon) return;
    
    // Set initial icon based on active theme
    const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
    updateThemeIcon(currentTheme);
    
    themeToggle.addEventListener("click", () => {
        const activeTheme = document.documentElement.getAttribute("data-theme") || "dark";
        const newTheme = activeTheme === "dark" ? "light" : "dark";
        
        document.documentElement.setAttribute("data-theme", newTheme);
        localStorage.setItem("theme", newTheme);
        updateThemeIcon(newTheme);
    });
    
    function updateThemeIcon(theme) {
        if (theme === "light") {
            themeIcon.className = "fa-solid fa-sun";
            themeIcon.style.color = "#eab308"; // Warm yellow for sun
        } else {
            themeIcon.className = "fa-solid fa-moon";
            themeIcon.style.color = ""; // Default text color
        }
    }
});


