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
    const aboutModal = document.getElementById('about-modal');
    const aboutClose = document.getElementById('about-close');
    const closeModal = document.querySelector('.close');
    const thinkingMessage = document.getElementById('thinking-message');
    const scorecardLink = document.getElementById('scorecard-link');
    const scorecardModal = document.getElementById('scorecard-modal');
    const scorecardClose = document.getElementById('scorecard-close');
    
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

    async function resetConversation() {
        try {
            // Start the suction animation if we're in answer view
            if (answerView.classList.contains('active')) {
                answerView.classList.add('sucking');
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
            
            // Reset thinking message
            if (thinkingMessage) {
                thinkingMessage.classList.remove('show');
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
    
    // Modal controls
    aboutLink.addEventListener('click', (e) => {
        e.preventDefault();
        showAboutModal();
    });
    
    // Event listener for about close button
    aboutClose.addEventListener('click', hideAboutModal);
    
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
        if (e.target === aboutModal) {
            hideAboutModal();
        }
        if (e.target === scorecardModal) {
            hideScorecardModal();
        }
    });

    // Close modals on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (aboutModal.style.display === 'block') {
                hideAboutModal();
            }
            if (scorecardModal.style.display === 'block') {
                hideScorecardModal();
            }
        }
    });

    // Function to show about modal with animation
    function showAboutModal() {
        aboutModal.style.display = 'block';
        
        // Trigger the animation after a brief delay
        setTimeout(() => {
            aboutModal.classList.add('show');
        }, 10);

        // Prevent background scrolling
        document.body.style.overflow = 'hidden';
    }

    // Function to hide about modal with animation
    function hideAboutModal() {
        aboutModal.classList.remove('show');
        aboutModal.classList.add('hide');
        
        // Wait for animation to complete before hiding
        setTimeout(() => {
            aboutModal.style.display = 'none';
            aboutModal.classList.remove('hide');
            document.body.style.overflow = 'auto';
        }, 600); // Match animation duration
    }

    
});