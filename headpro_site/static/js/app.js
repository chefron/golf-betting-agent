document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const initialView = document.getElementById('initial-view');
    const answerView = document.getElementById('answer-view');
    const initialInput = document.getElementById('initial-input');
    const initialSendBtn = document.getElementById('initial-send-btn');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const resetBtn = document.getElementById('reset-btn');
    const userQuestion = document.getElementById('user-question');
    const headProAnswer = document.getElementById('head-pro-answer');
    const aboutLink = document.getElementById('about-link');
    const thinkingMessage = document.getElementById('thinking-message');
    const scorecardLink = document.getElementById('scorecard-link');
    const scorecardModal = document.getElementById('scorecard-modal');
    const scorecardClose = document.getElementById('scorecard-close');

    // Global variables for subtitle management
    let aboutVideo = null;
    let subtitleInterval = null;
    let currentSubtitleIndex = -1;

    // Function to start tracking subtitles
    function startSubtitleTracking() {
        if (subtitleInterval) {
            clearInterval(subtitleInterval);
        }
        
        subtitleInterval = setInterval(() => {
            if (aboutVideo && !aboutVideo.paused) {
                updateSubtitles();
            }
        }, 100); // Check every 100ms for smooth subtitle updates
    }

    // Subtitle data structure - you'll need to fill in the actual timings and text
    const aboutSubtitles = [
        { start: 0, end: 3, text: "Well, well. Look who's curious about the Head Pro." },
        { start: 3.5, end: 7, text: "I'm not your typical golf analyst, that's for damn sure." },
        { start: 7.5, end: 11, text: "While everyone else is obsessing over strokes gained..." },
        { start: 11.5, end: 15, text: "I'm tracking what really matters - the mental game." },
        { start: 15.5, end: 19, text: "Every interview, every social media post, every tell..." },
        { start: 19.5, end: 23, text: "I see the psychological cracks others miss." },
        { start: 23.5, end: 27, text: "That's how I find the betting edges that matter." },
        { start: 27.5, end: 31, text: "The kind that separate the sharp money from the suckers." },
        { start: 31.5, end: 36, text: "Now ask me something useful about this week's field." }
    ];
    
    // Define SVG content as constants to ensure consistency when restoring
    const SEND_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="22" y1="2" x2="11" y2="13"></line>
        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
    </svg>`;
    
    const LOADING_ICON = '⟳';
    
    // Generate/retrieve user ID
    const userId = localStorage.getItem('userId') || 
        `user_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
    localStorage.setItem('userId', userId);

    // Get video element
    const headProVideos = {
    whiskey: document.querySelector('#whiskey-video'),
    cigar: document.querySelector('#cigar-video'),
    notebook: document.querySelector('#notebook-video')
    };
    const headProImgContainer = document.querySelector('.head-pro-img-container');
    
    let currentVideo = headProVideos.whiskey; // Start with whiskey video as default

    // Function to randomly select and show a video
    function selectRandomVideo() {
        const videoNames = ['whiskey', 'cigar', 'notebook'];
        const randomName = videoNames[Math.floor(Math.random() * videoNames.length)];
        
        console.log(`Random selection: ${randomName}`);
        console.log('Available videos:', Object.keys(headProVideos));
        console.log('Whiskey video element:', headProVideos.whiskey);
        console.log('Selected video element:', headProVideos[randomName]);
        
        // Hide all videos
        Object.values(headProVideos).forEach(video => {
            if (video) {
                video.style.display = 'none';
                video.pause();
                video.currentTime = 0;
            }
        });
        
        // Show and set the selected video
        currentVideo = headProVideos[randomName];
        if (currentVideo) {
            currentVideo.style.display = 'block';
            currentVideo.currentTime = 0;
            console.log(`Successfully set ${randomName} video to display: block`);
        } else {
            console.error(`Failed to find video element for: ${randomName}`);
        }
        
        return currentVideo;
    }

    // Update the startLoadingVideo function
    function startLoadingVideo() {
        // Select a random video first
        const videoToPlay = selectRandomVideo();
        
        if (videoToPlay) {
            videoToPlay.currentTime = 0;
            videoToPlay.play().catch(e => {
                console.error("Video play failed:", e);
            });
        }
    }

    if (headProVideos.whiskey || headProVideos.cigar || headProVideos.notebook) {
        console.log('Video elements found');

        // Set all videos to first frame and pause
        Object.values(headProVideos).forEach(video => {
            if (video) {
                video.currentTime = 0;
                video.pause();
                
                // Add event listener for when any video ends
                video.addEventListener('ended', function() {
                    console.log('Video ended, pausing on final frame');
                    // The fade-out will now be handled by stopLoadingVideo() when the response comes back
                });
            }
        });
        
        // Set whiskey as the default visible video
        currentVideo = headProVideos.whiskey;
        if (currentVideo) {
            currentVideo.style.display = 'block';
        }
    }

    // Update the stopLoadingVideo function to handle the fade-out
    function stopLoadingVideo() {
        document.body.classList.remove('loading');
        
        if (headProImgContainer) {
            headProImgContainer.classList.add('fade-out');
            
            setTimeout(() => {
                headProImgContainer.classList.add('hidden');
            }, 1000);
        }
        
        // Pause the current video
        if (currentVideo) {
            setTimeout(() => {
                currentVideo.pause();
            }, 300);
        }
    }
    
    // Load previous message if exists
    function loadLastMessage() {
        const savedMessages = localStorage.getItem(`headpro_messages_${userId}`);
        
        if (savedMessages) {
            try {
                const messages = JSON.parse(savedMessages);
                if (messages && messages.length > 0) {
                    // Show the last question and answer
                    showAnswerView(
                        messages[messages.length - 2]?.text || "", // Last user message
                        messages[messages.length - 1]?.text || ""  // Last assistant message
                    );
                    
                    // If returning to an existing conversation, already be zoomed
                    document.body.classList.add('zoomed');
                }
            } catch (e) {
                console.error('Error loading saved messages:', e);
                localStorage.removeItem(`headpro_messages_${userId}`);
            }
        }
    }
    
    // Switch to answer view
    function showAnswerView(question, answer) {
        userQuestion.textContent = question;
        headProAnswer.innerHTML = answer;
        
        initialView.classList.remove('active');
        answerView.classList.add('active');

        // Auto-scroll the answer area to the top
        headProAnswer.scrollTop = 0;
        
        // Focus on the input
        messageInput.focus();
    }
    
    // Switch to initial view
    function showInitialView() {
        initialView.classList.add('active');
        answerView.classList.remove('active');
        
        // Clear inputs
        initialInput.value = '';
        messageInput.value = '';
        
        // Reset button states explicitly
        resetSendButtons();
        
        // Focus on the initial input
        initialInput.focus();
    }
    
    // Helper function to ensure send buttons are in their correct state
    function resetSendButtons() {
        // Reset initial send button
        initialSendBtn.innerHTML = SEND_SVG;
        initialSendBtn.classList.remove('loading');
        initialSendBtn.disabled = false;
        
        // Reset main send button
        sendBtn.innerHTML = SEND_SVG;
        sendBtn.classList.remove('loading');
        sendBtn.disabled = false;
    }
    
    // Save messages to localStorage
    function saveMessages(question, answer) {
        const messages = [];
        
        // Add previous messages if available
        try {
            const savedMessages = localStorage.getItem(`headpro_messages_${userId}`);
            if (savedMessages) {
                messages.push(...JSON.parse(savedMessages));
            }
        } catch (e) {
            console.error('Error loading previous messages:', e);
        }
        
        // Add new messages
        messages.push(
            { text: question, sender: 'user' },
            { text: answer, sender: 'assistant' }
        );
        
        // Limit number of saved messages to prevent localStorage overflow
        const maxMessages = 50; // 25 exchanges
        if (messages.length > maxMessages) {
            messages.splice(0, messages.length - maxMessages);
        }
        
        // Save to localStorage
        localStorage.setItem(`headpro_messages_${userId}`, JSON.stringify(messages));
    }
    
    // Send message to API
    async function sendMessage(message, isInitial = false) {
        if (!message.trim()) return;

        document.body.classList.add('loading')
        
        // Get the correct button
        const targetBtn = isInitial ? initialSendBtn : sendBtn;
        
        // Set to loading state
        targetBtn.innerHTML = LOADING_ICON;
        targetBtn.classList.add('loading');
        targetBtn.disabled = true;

        // Show thinking message when starting to load
        if (isInitial && thinkingMessage) {
            thinkingMessage.classList.add('show');
        }

        // START the loading video
        startLoadingVideo();
        
        // Begin cinematic zoom when sending first message
        if (isInitial) {
            document.body.classList.add('pre-zoom');
            void document.body.offsetHeight; // Force reflow
            setTimeout(() => {
                document.body.classList.remove('pre-zoom');
                document.body.classList.add('zooming');
            }, 20);
        }
        
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, message })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            // Debug formatting
            console.log(JSON.stringify(data.response));
            
            // Save messages
            saveMessages(message, data.response);
            
            // Show answer view
            showAnswerView(message, data.response);

            if (isInitial) {
                document.querySelector('.chat-content').classList.add('conversation-started');
            }
                        
            // After zoom animation completes, switch to the static zoomed class
            if (isInitial) {
                setTimeout(() => {
                    document.body.classList.remove('zooming');
                    document.body.classList.add('zoomed');
                }, 3000);
            }
            
        } catch (error) {
            console.error('Error sending message:', error);
            
            // Show error in answer view
            showAnswerView(
                message, 
                "The Head Pro seems to have wandered off to the 19th hole. Try again in a moment."
            );
            
            // Complete the zoom even on error
            if (isInitial) {
                setTimeout(() => {
                    document.body.classList.remove('zooming');
                    document.body.classList.add('zoomed');
                }, 5000);
            }

        } finally {
            // Reset UI state
            setTimeout(() => {
                // Hide thinking message
                if (thinkingMessage) {
                    thinkingMessage.classList.remove('show');
                }
                
                // Restore the original SVG content
                targetBtn.innerHTML = SEND_SVG;
                targetBtn.classList.remove('loading');
                targetBtn.disabled = false;

                // Stop the loading video
                stopLoadingVideo();
                
                // Clear the input field
                if (!isInitial) {
                    messageInput.value = '';
                }
            }, 300); // Slightly longer delay to ensure transitions complete
        }
    }

        function stopSubtitleTracking() {
        if (subtitleInterval) {
            clearInterval(subtitleInterval);
            subtitleInterval = null;
        }
        currentSubtitleIndex = -1;
        
        const subtitleElement = document.getElementById('thinking-message');
        if (subtitleElement) {
            subtitleElement.classList.remove('show', 'subtitle-mode');
            subtitleElement.textContent = '';
            subtitleElement.style.opacity = '';
            subtitleElement.style.display = '';
        }
    }

    async function resetConversation() {
        try {

            stopSubtitleTracking();

            cleanupAboutVideo();

            // Start the suction animation if we're in answer view
            if (answerView.classList.contains('active')) {
                answerView.classList.add('sucking');
            }
            
            // Reset thinking message COMPLETELY - remove all classes and content
            if (thinkingMessage) {
                thinkingMessage.classList.remove('show', 'subtitle-mode');
                thinkingMessage.textContent = ''; // Clear any existing text
                thinkingMessage.style.opacity = ''; // Reset any inline styles
            }

            // Start unzooming with a brief delay
            setTimeout(() => {
                document.body.classList.add('unzooming');
            }, 300);
            
            // Start API reset and other cleanup in parallel
            const resetPromise = fetch('/api/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId })
            });
            
            // Clear saved messages
            localStorage.removeItem(`headpro_messages_${userId}`);
            
            // Reset button states explicitly
            resetSendButtons();

            // Reset about video if it's playing - BEFORE resetting other videos
            if (aboutVideo) {
                aboutVideo.pause();
                aboutVideo.currentTime = 0;
                aboutVideo.style.display = 'none';
                
                // Hide video controls
                const videoControls = document.getElementById('video-controls-overlay');
                if (videoControls) {
                    videoControls.style.display = 'none';
                    videoControls.classList.remove('about-video-active');
                }
            }
            
            // Reset the Head Pro container
            const headProImgContainer = document.querySelector('.head-pro-img-container');
            if (headProImgContainer) {
                headProImgContainer.classList.remove('fade-out', 'hidden');
            
                // Reset to whiskey video as default
                Object.values(headProVideos).forEach(video => {
                    if (video) {
                        video.style.display = 'none';
                        video.pause();
                        video.currentTime = 0;
                    }
                });
                
                currentVideo = headProVideos.whiskey;
                if (currentVideo) {
                    currentVideo.style.display = 'block';
                    currentVideo.currentTime = 0;
                }
            }

            // Rest of the function stays the same...

            // Reset welcome message visibility
            const welcomeTagline = document.querySelector('.welcome-tagline');
            const welcomePrompt = document.querySelector('.welcome-prompt');

            if (welcomeTagline && welcomePrompt) {
                // Set opacity back to 1 (will be visible because we removed conversation-started class)
                welcomeTagline.style.opacity = '1';
                welcomePrompt.style.opacity = '1';
                
                // Remove any inline styles after transition completes
                setTimeout(() => {
                    welcomeTagline.style.opacity = '';
                    welcomePrompt.style.opacity = '';
                }, 100);
            }
            
            // Wait for suction animation to complete
            await new Promise(resolve => setTimeout(resolve, 800));
            
            // Mark as completely sucked
            if (answerView.classList.contains('active')) {
                answerView.classList.add('sucked');
            }
            
            // Wait for API reset to complete
            await resetPromise;
            
            // After transition, remove all zoom classes and reset answer view
            setTimeout(() => {
                document.body.classList.remove('zoomed', 'zooming', 'unzooming');
                
                // Clean up the answer view classes
                answerView.classList.remove('sucking', 'sucked');

                // Remove the conversation-started class
                const chatContent = document.querySelector('.chat-content');
                if (chatContent) {
                    chatContent.classList.remove('conversation-started');
                }
                    
                // Show initial view
                showInitialView();
            }, 1000);
            
        } catch (error) {
            console.error('Error resetting conversation:', error);
            headProAnswer.textContent = "Couldn't reset the conversation. The Head Pro might be having technical difficulties.";
        }
    }
    
    // Event Listeners
    initialSendBtn.addEventListener('click', () => {
        sendMessage(initialInput.value, true);
    });
    
    initialInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage(initialInput.value, true);
    });
    
    sendBtn.addEventListener('click', () => {
        sendMessage(messageInput.value);
    });
    
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage(messageInput.value);
        }
    });
    
    resetBtn.addEventListener('click', resetConversation);
    
    // Update the about link event listener
    aboutLink.addEventListener('click', (e) => {
        e.preventDefault();
        
        // Check if we're already in about mode (video playing)
        if (aboutVideo && !aboutVideo.paused && aboutVideo.currentTime > 0) {
            // If about video is playing, restart it
            aboutVideo.currentTime = 0;
            aboutVideo.play();
        } else {
            // Start the about video experience
            startAboutVideo();
        }
    });

    // Add mute button event listener
    document.addEventListener('click', (e) => {
        if (e.target.id === 'about-mute-btn') {
            toggleAboutVideoSound();
        }
    });
    
    // Ensure buttons are in their correct initial state
    resetSendButtons();
    
    // Initialize
    loadLastMessage();
    
    // If no saved message, focus on initial input
    if (initialView.classList.contains('active')) {
        initialInput.focus();
    }

    // Function to load scorecard data
    async function loadScorecardData() {
        try {
            const response = await fetch('/api/scorecard-data');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            
            // Update overview data
            updateOverviewData(data.overview);
            
            // Update bet history
            updateBetHistory(data.bet_history);
            
        } catch (error) {
            console.error('Error loading scorecard data:', error);
            
            // Show error message in the table
            const overviewRow = document.getElementById('overview-row');
            if (overviewRow) {
                overviewRow.innerHTML = '<td colspan="9" style="text-align: center; color: var(--ink-red);">Error loading data</td>';
            }
            
            const betHistoryTbody = document.getElementById('bet-history-tbody');
            if (betHistoryTbody) {
                betHistoryTbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--ink-red);">Error loading betting history</td></tr>';
            }
        }
    }

    // Function to update overview data
    function updateOverviewData(overview) {
        const overviewRow = document.getElementById('overview-row');
        if (!overviewRow || !overview) return;

        const totalBets = overview.total_bets || 0;
        const profitLoss = overview.profit_loss_units || 0;
        const roi = overview.roi || 0;
        const avgStake = overview.avg_stake_units || 0;
        const avgOdds = overview.avg_odds_american || '-';
        const avgEv = overview.avg_ev || 0;

        // Determine classes for positive/negative values
        const profitLossClass = profitLoss > 0 ? 'positive' : profitLoss < 0 ? 'negative' : '';
        const roiClass = roi > 0 ? 'positive' : roi < 0 ? 'negative' : '';
        const avgEvClass = avgEv > 0 ? 'positive' : avgEv < 0 ? 'negative' : '';

        overviewRow.innerHTML = `
            <td>${totalBets}</td>
            <td class="${profitLossClass}">${profitLoss > 0 ? '+' : ''}${profitLoss}u</td>
            <td class="${roiClass}">${roi > 0 ? '+' : ''}${roi}%</td>
            <td>${avgStake}u</td>
            <td>${avgOdds}</td>
            <td class="${avgEvClass}">${avgEv > 0 ? '+' : ''}${avgEv}%</td>
            <td colspan="3"></td>
        `;
    }

    // Function to update bet history
    function updateBetHistory(betHistory) {
        const betHistoryTbody = document.getElementById('bet-history-tbody');
        if (!betHistoryTbody) return;

        if (!betHistory || betHistory.length === 0) {
            betHistoryTbody.innerHTML = '<tr><td colspan="9" style="text-align: center; padding: 2rem; color: var(--ink-faded); font-style: italic;">No betting history available yet.</td></tr>';
            return;
        }

        // Generate HTML for each bet
        const betsHtml = betHistory.map(bet => {
            const outcomeClass = `outcome-${bet.outcome}`;
            const profitLossClass = bet.profit_loss_units > 0 ? 'profit-positive' : bet.profit_loss_units < 0 ? 'profit-negative' : '';
            
            return `
                <tr>
                    <td>${bet.settled_date}</td>
                    <td class="tournament-name">${bet.event_name}</td>
                    <td class="player-name">${bet.player_name}</td>
                    <td>${bet.bet_market}</td>
                    <td>${bet.american_odds}</td>
                    <td>${bet.stake_units}u</td>
                    <td class="${outcomeClass}">${bet.outcome.toUpperCase()}</td>
                    <td class="${profitLossClass}">${bet.profit_loss_display}</td>
                    <td class="mental-score">${bet.mental_form_score}</td>
                </tr>
            `;
        }).join('');

        betHistoryTbody.innerHTML = betsHtml;
    }

    // Function to show scorecard modal with animation
    function showScorecardModal() {
        // Load the data first
        loadScorecardData();
        
        // Show the modal
        scorecardModal.style.display = 'block';
        
        // Trigger the animation after a brief delay to ensure display: block has taken effect
        setTimeout(() => {
            scorecardModal.classList.add('show');
        }, 10);

        // Prevent background scrolling
        document.body.style.overflow = 'hidden';
    }

    // Function to hide scorecard modal with animation
    function hideScorecardModal() {
        scorecardModal.classList.remove('show');
        scorecardModal.classList.add('hide');
        
        // Wait for animation to complete before hiding
        setTimeout(() => {
            scorecardModal.style.display = 'none';
            scorecardModal.classList.remove('hide');
            document.body.style.overflow = 'auto';
        }, 600); // Match this to your hide animation duration
    }

    // Event listeners for scorecard modal
    scorecardLink.addEventListener('click', (e) => {
        e.preventDefault();
        showScorecardModal();
    });

    scorecardClose.addEventListener('click', hideScorecardModal);

    // Close modals when clicking outside them
    window.addEventListener('click', (e) => {
        if (e.target === scorecardModal) {
            hideScorecardModal();
        }
    });

    // Close modals on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (scorecardModal.style.display === 'block') {
                hideScorecardModal();
            }
        }
    });

    // Function to initialize about video elements
    function initializeAboutVideo() {
        // Create the about video element if it doesn't exist
        if (!aboutVideo) {
            aboutVideo = document.createElement('video');
            aboutVideo.id = 'about-video';
            aboutVideo.className = 'head-pro-video';
            aboutVideo.muted = true; // Start muted by default
            aboutVideo.preload = 'auto';
            aboutVideo.playsInline = true;
            aboutVideo.style.display = 'none';
            
            // Add video source
            const source = document.createElement('source');
            source.src = '/static/videos/about.mp4'; // Adjust path as needed
            source.type = 'video/mp4';
            aboutVideo.appendChild(source);
            
            // Add video controls (hidden by default)
            aboutVideo.controls = false;
            
            // Add to the video wrapper
            const videoWrapper = document.querySelector('.head-pro-img-wrapper');
            if (videoWrapper) {
                videoWrapper.appendChild(aboutVideo);
            }
            
            // Add event listeners
            aboutVideo.addEventListener('loadedmetadata', onAboutVideoLoaded);
            aboutVideo.addEventListener('timeupdate', updateSubtitles);
            aboutVideo.addEventListener('ended', onAboutVideoEnded);
            aboutVideo.addEventListener('pause', onAboutVideoPaused);
            aboutVideo.addEventListener('play', onAboutVideoPlayed);
        }
    }

    // Add about video functionality
    initializeAboutVideo();

    // Replace your existing startAboutVideo() function with this fixed version:

    function startAboutVideo() {
        console.log('Starting about video experience');
        
        // Begin the zoom animation (reuse existing logic)
        document.body.classList.add('pre-zoom');
        void document.body.offsetHeight; // Force reflow
        setTimeout(() => {
            document.body.classList.remove('pre-zoom');
            document.body.classList.add('zooming');
        }, 20);
        
        // Hide welcome messages - but DON'T use 'loading' class for about video
        // Instead, directly hide the welcome elements
        const welcomeTagline = document.querySelector('.welcome-tagline');
        const welcomePrompt = document.querySelector('.welcome-prompt');
        const inputArea = document.querySelector('.centered-input-area');
        
        if (welcomeTagline) welcomeTagline.style.opacity = '0';
        if (welcomePrompt) welcomePrompt.style.opacity = '0';
        if (inputArea) inputArea.style.opacity = '0';
        
        // Hide all other videos and show about video
        Object.values(headProVideos).forEach(video => {
            if (video) {
                video.style.display = 'none';
                video.pause();
                video.currentTime = 0;
            }
        });
        
        // Show and prepare about video
        if (aboutVideo) {
            aboutVideo.style.display = 'block';
            aboutVideo.currentTime = 0;
            aboutVideo.muted = true; // Ensure it starts muted
            currentSubtitleIndex = -1;
            
            // Show video controls
            const videoControls = document.getElementById('video-controls-overlay');
            if (videoControls) {
                videoControls.style.display = 'block';
                // Add class to show controls during about video
                videoControls.classList.add('about-video-active');
            }

            // Also add click handler for the video itself to toggle pause/play
            if (aboutVideo) {
                aboutVideo.addEventListener('click', function() {
                    if (aboutVideo.paused) {
                        aboutVideo.play();
                        console.log('Video resumed');
                    } else {
                        aboutVideo.pause();
                        console.log('Video paused');
                    }
                });
            }
            
            // Show subtitle area with subtitle styling
            const subtitleElement = document.getElementById('thinking-message');
            if (subtitleElement) {
                subtitleElement.classList.add('show', 'subtitle-mode');
                subtitleElement.textContent = ''; // Clear any existing text
            }
            
            // Update mute button
            updateMuteButton();

            const muteBtn = document.getElementById('about-mute-btn');
            if (muteBtn) {
                console.log('Mute button found');
                muteBtn.onclick = function(e) {
                    e.stopPropagation();
                    toggleAboutVideoSound();
                    console.log('Mute button clicked, video muted:', aboutVideo.muted);
                };
            } else {
                console.error('Mute button not found!');
            }

            // Start video
            aboutVideo.play().catch(e => {
                console.error("About video play failed:", e);
            });
            
            // Start subtitle tracking
            startSubtitleTracking();
        }
        
        // Show input after 10 seconds
        setTimeout(() => {
            showAboutInput();
        }, 10000);
        
        // Complete zoom after animation - but DON'T remove loading class
        setTimeout(() => {
            document.body.classList.remove('zooming');
            document.body.classList.add('zoomed');
            // REMOVED: document.body.classList.remove('loading'); 
            // This was causing the welcome elements to reappear
        }, 3000);
    }

    // Enhanced subtitle update function
    function updateSubtitles() {
        if (!aboutVideo) return;

        // Only update subtitles if about video is visible and playing
        if (aboutVideo.style.display === 'none' || aboutVideo.paused) {
            return;
        }
        
        const currentTime = aboutVideo.currentTime;
        const subtitleElement = document.getElementById('thinking-message');
        
        if (!subtitleElement) return;
        
        // Find the current subtitle
        let newSubtitleIndex = -1;
        for (let i = 0; i < aboutSubtitles.length; i++) {
            const subtitle = aboutSubtitles[i];
            if (currentTime >= subtitle.start && currentTime <= subtitle.end) {
                newSubtitleIndex = i;
                break;
            }
        }
        
        // Update subtitle if it changed
        if (newSubtitleIndex !== currentSubtitleIndex) {
            currentSubtitleIndex = newSubtitleIndex;
            
            if (newSubtitleIndex >= 0) {
                // Add a subtle fade effect for subtitle changes
                subtitleElement.style.opacity = '0';
                setTimeout(() => {
                    subtitleElement.textContent = aboutSubtitles[newSubtitleIndex].text;
                    subtitleElement.style.opacity = '1';
                }, 150);
            } else {
                subtitleElement.textContent = '';
            }
        }
    }

    function showAboutInput() {
        // Don't switch views at all - just show the input in the current initial view
        
        // Find or create an input area in the initial view
        let aboutInputArea = document.getElementById('about-input-area');
        
        if (!aboutInputArea) {
            // Create the input area
            aboutInputArea = document.createElement('div');
            aboutInputArea.id = 'about-input-area';
            aboutInputArea.className = 'input-area';
            aboutInputArea.style.cssText = `
                position: fixed;
                bottom: 10%;
                left: 50%;
                transform: translateX(-50%);
                width: 75%;
                max-width: 600px;
                z-index: 100;
                pointer-events: auto;
            `;
            
            // Create the input container
            const inputContainer = document.createElement('div');
            inputContainer.className = 'input-container';
            
            // Create the input
            const input = document.createElement('input');
            input.type = 'text';
            input.id = 'about-input';
            input.placeholder = 'Ask me something...';
            input.style.cssText = `
                flex: 1;
                width: 100%;
                padding: 12px 16px;
                padding-right: 50px;
                border: none;
                border-radius: 20px;
                background: rgba(255,255,255,0.1);
                color: var(--white);
                font-family: "Merriweather", serif;
                font-optical-sizing: auto;
            `;
            
            // Create the send button
            const sendBtn = document.createElement('button');
            sendBtn.className = 'send-icon-btn';
            sendBtn.id = 'about-send-btn';
            sendBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13"></line>
                    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                </svg>
            `;
            
            // Assemble the input area
            inputContainer.appendChild(input);
            inputContainer.appendChild(sendBtn);
            aboutInputArea.appendChild(inputContainer);
            
            // Add to the main chat container instead of initial view
            const chatContainer = document.querySelector('.chat-container');
            if (chatContainer) {
                chatContainer.appendChild(aboutInputArea);
            }
            
            // Add event listeners
            sendBtn.addEventListener('click', () => {
                const message = input.value.trim();
                if (message) {
                    cleanupAboutVideo();
                    sendMessage(message);
                }
            });
            
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    const message = input.value.trim();
                    if (message) {
                        cleanupAboutVideo();
                        sendMessage(message);
                    }
                }
            });
            
            // Focus styles
            input.addEventListener('focus', () => {
                input.style.background = 'rgba(255,255,255,0.15)';
            });
            
            input.addEventListener('blur', () => {
                input.style.background = 'rgba(255,255,255,0.1)';
            });
        }
        
        // Show the input area with a fade-in effect
        aboutInputArea.style.opacity = '0';
        aboutInputArea.style.display = 'flex';
        
        setTimeout(() => {
            aboutInputArea.style.transition = 'opacity 0.5s ease';
            aboutInputArea.style.opacity = '1';
        }, 100);
        
        // Focus on the input
        const input = aboutInputArea.querySelector('input');
        if (input) {
            setTimeout(() => input.focus(), 200);
        }
    }

    // Event handlers for about video
    function onAboutVideoLoaded() {
        console.log('About video metadata loaded');
    }

    function onAboutVideoEnded() {
        console.log('About video ended');
        
        // Stop subtitle tracking
        if (subtitleInterval) {
            clearInterval(subtitleInterval);
            subtitleInterval = null;
        }
        
        // Clear subtitles
        const subtitleElement = document.getElementById('thinking-message');
        if (subtitleElement) {
            subtitleElement.classList.remove('show');
            subtitleElement.textContent = '';
        }
        
        // Keep the video visible but paused
        if (aboutVideo) {
            aboutVideo.pause();
        }
    }

    function onAboutVideoPaused() {
        console.log('About video paused');
        // Stop subtitle tracking when paused
        if (subtitleInterval) {
            clearInterval(subtitleInterval);
            subtitleInterval = null;
        }
    }

    function onAboutVideoPlayed() {
        console.log('About video playing');
        // Resume subtitle tracking when playing
        startSubtitleTracking();
    }

    // Function to toggle video sound
    function toggleAboutVideoSound() {
        if (aboutVideo) {
            aboutVideo.muted = !aboutVideo.muted;
            console.log('About video muted:', aboutVideo.muted);
            
            // Update mute button if it exists
            updateMuteButton();
        }
    }

    // Function to update mute button appearance
    function updateMuteButton() {
        const muteButton = document.getElementById('about-mute-btn');
        if (muteButton && aboutVideo) {
            // Update button icon/text based on mute state
            if (aboutVideo.muted) {
                muteButton.innerHTML = '🔇'; // Muted icon
                muteButton.title = 'Unmute video';
            } else {
                muteButton.innerHTML = '🔊'; // Sound icon
                muteButton.title = 'Mute video';
            }
        }
    }

    function cleanupAboutVideo() {

        stopSubtitleTracking();

        // Remove the about input area
        const aboutInputArea = document.getElementById('about-input-area');
        if (aboutInputArea) {
            aboutInputArea.remove();
        }
        
        // Hide about video and controls
        if (aboutVideo) {
            aboutVideo.style.display = 'none';
            aboutVideo.pause();
        }
        
        const videoControls = document.getElementById('video-controls-overlay');
        if (videoControls) {
            videoControls.style.display = 'none';
            videoControls.classList.remove('about-video-active');
        }
 
        // Only start loading video if NOT during a reset
        // Check if we're in a reset state by looking for the unzooming class
        if (!document.body.classList.contains('unzooming')) {
            // Show a random loading video for the next chat response
            startLoadingVideo();
        
            // NOW mark conversation as started since they're sending a real message
            const chatContent = document.querySelector('.chat-content');
            if (chatContent) {
                chatContent.classList.add('conversation-started');
            }
        }
    }
});