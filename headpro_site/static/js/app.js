document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const initialView = document.getElementById('initial-view');
    const answerView = document.getElementById('answer-view');
    const userQuestion = document.getElementById('user-question');
    const headProAnswer = document.getElementById('head-pro-answer');
    const aboutLink = document.getElementById('about-link');
    const thinkingMessage = document.getElementById('thinking-message');
    const scorecardLink = document.getElementById('scorecard-link');
    const scorecardModal = document.getElementById('scorecard-modal');
    const scorecardClose = document.getElementById('scorecard-close');
    const mainInput = document.getElementById('main-input');
    const mainSendBtn = document.getElementById('main-send-btn');
    const textareaAutoResize = setupTextareaAutoResize();

    // Add a flag to track if reset was called
    let resetCalled = false;
    
    // Rate limiting variables
    let lastApiCall = 0;
    let apiCallCount = 0;
    let rateLimitWindowStart = Date.now();
    const API_RATE_LIMIT = 10; // Max 10 API calls per minute
    const RATE_LIMIT_WINDOW = 60000; // 1 minute
    const MIN_TIME_BETWEEN_CALLS = 2000; // 2 seconds between calls

    // Global variables for subtitle management
    let aboutVideo = document.querySelector('#about-video');
    let subtitleInterval = null;
    let currentSubtitleIndex = -1;

    // Video management
    let switchingToAbout = false;
    let currentVideoMode = 'idle'; // 'idle', 'loading', 'about'

    // Preload about video for smoother transitions
    if (aboutVideo) {
        aboutVideo.addEventListener('loadeddata', () => {
            console.log('About video preloaded and ready');
        });
        // This will load the video metadata and first frame
        aboutVideo.load();
    }

    // Rate limiting function
    function isRateLimited() {
        const now = Date.now();
        
        // Reset counter if window has passed
        if (now - rateLimitWindowStart > RATE_LIMIT_WINDOW) {
            apiCallCount = 0;
            rateLimitWindowStart = now;
        }
        
        // Check if too many calls in window
        if (apiCallCount >= API_RATE_LIMIT) {
            return true;
        }
        
        // Check if too soon since last call
        if (now - lastApiCall < MIN_TIME_BETWEEN_CALLS) {
            return true;
        }
        
        return false;
    }

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
        { start: 0, end: 3.9, text: "They say golf is 90% mental" },
        { start: 4.2, end: 9, text: "but most bettors are still crunching ballstriking stats like it's 2015" },
        { start: 9.5, end: 13.9, text: "I don't give a damn about strokes gained off the tee or around the green" },
        { start: 14.2, end: 16.5, text: "I care about strokes gained between the ears" },
        { start: 16.9, end: 19, text: "That's where tournaments are won." },
        { start: 19.5, end: 23.2, text: "I scan every interview, every podcast, every social media meltdown" },
        { start: 23.5, end: 27, text: "to build psychological profiles no spreadsheet can capture" },
        { start: 27.5, end: 31, text: "When a guy's head ain't right, his game crumbles" },
        { start: 31.3, end: 34.5, text: "When he's locked in mentally, he exceeds expectations" },
        { start: 35, end: 37.5, text: "That, my friends, is what we call an edge." },
        { start: 38, end: 43, text: "I'm the Head Pro, and I'm here to change the way you bet on golf." }
    ];
    
    // Replace the SEND_SVG constant in app.js with the new golf tee icon (larger and centered)
    const SEND_SVG = `<svg width="22" height="40" viewBox="0 0 24 48" xmlns="http://www.w3.org/2000/svg">
    <path d="M6 0H18V2L14 6V28C14 33 13.5 40 12 44C10.5 40 10 33 10 28V6L6 2V0Z" fill="currentColor"/>
    </svg>`;

    // Since we want the tee to spin during loading, we use the same icon
    const LOADING_ICON = SEND_SVG;

    // Simple function to stop all videos immediately
    function stopAllVideos() {
        console.log('Stopping all videos');
        
        // Stop regular videos AND about video
        Object.values(headProVideos).forEach(video => {
            if (video) {
                video.pause();
                video.currentTime = 0;
                video.style.display = 'none';
            }
        });
        
        currentVideoMode = 'idle';
    }
    
    // Generate/retrieve user ID
    const userId = localStorage.getItem('userId') || 
        `user_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
    localStorage.setItem('userId', userId);

    // Get video element
    const headProVideos = {
    whiskey: document.querySelector('#whiskey-video'),
    cigar: document.querySelector('#cigar-video'),
    notebook: document.querySelector('#notebook-video'),
    about: document.querySelector('#about-video')
    };
    const headProImgContainer = document.querySelector('.head-pro-img-container');
    
    let currentVideo = headProVideos.whiskey; // Start with whiskey video as default

    // Simplified selectRandomVideo function
    function selectRandomVideo() {
        const videoNames = ['whiskey', 'cigar', 'notebook'];
        const randomName = videoNames[Math.floor(Math.random() * videoNames.length)];
        
        console.log(`Random selection: ${randomName}`);
        
        // Stop all videos first
        stopAllVideos();
        
        // Show and set the selected video
        currentVideo = headProVideos[randomName];
        if (currentVideo) {
            currentVideo.style.display = 'block';
            currentVideo.currentTime = 0;
            console.log(`Successfully set ${randomName} video to display: block`);
        }
        
        return currentVideo;
    }

    // Simplified startLoadingVideo function
    function startLoadingVideo() {
        // Don't start if we're in about mode or already loading
        if (switchingToAbout || currentVideoMode === 'loading' || currentVideoMode === 'about') {
            console.log('Skipping loading video - wrong mode:', currentVideoMode);
            return;
        }
        
        console.log('Starting loading video');
        currentVideoMode = 'loading';
        
        // Select a random video
        const videoToPlay = selectRandomVideo();
        
        if (videoToPlay) {
            videoToPlay.currentTime = 0;
            videoToPlay.play().catch(e => {
                console.error("Loading video play failed:", e);
            });
        }
    }

    // Simplified stopLoadingVideo function
    function stopLoadingVideo() {
        console.log('Stopping loading video');
        
        document.body.classList.remove('loading');
        
        // DON'T hide the video container if we're in the middle of a reset
        const isResetting = document.body.classList.contains('unzooming') || 
                        !answerView.classList.contains('active');
        
        if (headProImgContainer && !isResetting) {
            headProImgContainer.classList.add('fade-out');
            
            setTimeout(() => {
                headProImgContainer.classList.add('hidden');
            }, 1000);
        } else {
            console.log('Skipping video hide because we are resetting');
        }
        
        // Only stop if we're in loading mode
        if (currentVideoMode === 'loading') {
            if (currentVideo) {
                setTimeout(() => {
                    currentVideo.pause();
                }, 300);
            }
            currentVideoMode = 'idle';
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

    function truncateUserQuestion(question, maxLength = 50) {
        if (question.length <= maxLength) {
            return question;
        }
        
        // Find the last space before the limit to avoid cutting words
        const truncated = question.substring(0, maxLength);
        const lastSpace = truncated.lastIndexOf(' ');
        
        if (lastSpace > 0) {
            return question.substring(0, lastSpace) + '...';
        }
        
        return truncated + '...?';
    }
    
    function showAnswerView(question, answer) {
        
        // Reset any inline opacity styles that might have been set
        const userQuestion = document.getElementById('user-question');
        const headProAnswer = document.getElementById('head-pro-answer');
        const controls = document.querySelector('#answer-view .controls');
        
        if (userQuestion) userQuestion.style.opacity = '';
        if (headProAnswer) headProAnswer.style.opacity = '';
        if (controls) controls.style.opacity = '';
        
        // Truncate the question before displaying
        const truncatedQuestion = truncateUserQuestion(question);
        userQuestion.textContent = truncatedQuestion;

        headProAnswer.textContent = answer;
        
        initialView.classList.remove('active');
        answerView.classList.add('active');

        // Auto-scroll the answer area to the top
        headProAnswer.scrollTop = 0;
        
        // Ensure message input is enabled and ready
        mainInput.disabled = false;
        mainInput.style.opacity = '';
        mainInput.style.pointerEvents = '';
        mainInput.focus();
    }
    
    // Switch to initial view
    function showInitialView() {
        initialView.classList.add('active');
        answerView.classList.remove('active');
        
        // Clear inputs
        mainInput.value = ''
        
        // Reset button states explicitly
        resetSendButtons();
        
        // Focus on the initial input
        mainInput.focus();
    }
    
    // Helper function to ensure send buttons are in their correct state
    function resetSendButtons() {
    if (mainSendBtn) {
            mainSendBtn.innerHTML = SEND_SVG;
            mainSendBtn.classList.remove('loading');
            mainSendBtn.disabled = false;
            mainSendBtn.style.pointerEvents = '';
            mainSendBtn.style.cursor = '';
        }
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
    
    async function sendMessage(message, isInitial = false) {
        if (!message.trim()) return;

        // Reset the flag at the start of new messages
        resetCalled = false;

        // Rate limiting check
        if (isRateLimited()) {
            console.log('Message rate limited');
            const rateLimitMessage = "Easy there, tiger. Give me a moment to catch up before firing off another question.";
            showAnswerView(message, rateLimitMessage);
            
            if (isInitial) {
                document.querySelector('.chat-content').classList.add('conversation-started');
                document.body.classList.add('pre-zoom');
                void document.body.offsetHeight;
                setTimeout(() => {
                    document.body.classList.remove('pre-zoom');
                    document.body.classList.add('zooming');
                }, 20);
                setTimeout(() => {
                    document.body.classList.remove('zooming');
                    document.body.classList.add('zoomed');
                }, 3000);
            }
            
            mainInput.disabled = false;
            mainInput.style.opacity = '';
            mainInput.style.pointerEvents = '';
            mainInput.value = '';
            if (textareaAutoResize) textareaAutoResize();
            resetSendButtons();
            
            return;
        }

        // Update rate limiting counters
        lastApiCall = Date.now();
        apiCallCount++;
        console.log('API call made, count:', apiCallCount);

        document.body.classList.add('loading')
        
        // Disable input during loading
        mainInput.disabled = true;
        mainInput.style.opacity = '0.5';
        mainInput.style.pointerEvents = 'none';
        
        // Get the button
        const targetBtn = mainSendBtn;
        
        // Set to loading state
        targetBtn.innerHTML = LOADING_ICON;
        targetBtn.classList.add('loading');
        targetBtn.disabled = true;
        targetBtn.style.pointerEvents = 'none';
        targetBtn.style.cursor = 'default';

        // Show thinking message when starting to load (only for initial)
        if (isInitial && thinkingMessage) {
            thinkingMessage.classList.add('show');
        }

        // START the loading video
        startLoadingVideo();
        
        // Begin cinematic zoom when sending first message
        if (isInitial) {
            document.body.classList.add('pre-zoom');
            void document.body.offsetHeight;
            setTimeout(() => {
                document.body.classList.remove('pre-zoom');
                document.body.classList.add('zooming');
            }, 20);
        }
        
        // Cancel any previous request
        if (currentAbortController) {
            currentAbortController.abort();
        }
        currentAbortController = new AbortController();
        
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, message }),
                signal: currentAbortController.signal
            });
            
            // CHECK: If reset was called while we were waiting, abandon everything
            if (resetCalled) {
                console.log('Reset was called during API request, abandoning response');
                return;
            }
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            // CHECK AGAIN: If reset was called while parsing response, abandon
            if (resetCalled) {
                console.log('Reset was called during response processing, abandoning');
                return;
            }
            
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
            if (error.name === 'AbortError' || resetCalled) {
                console.log('Request was cancelled or reset was called');
                return; // Don't show error message if cancelled
            }
            
            console.error('Error sending message:', error);
            
            showAnswerView(
                message, 
                "The Head Pro seems to have wandered off to the 19th hole. Try again in a moment."
            );
            
            if (isInitial) {
                setTimeout(() => {
                    document.body.classList.remove('zooming');
                    document.body.classList.add('zoomed');
                }, 5000);
            }

        } finally {
            // ONLY reset UI if reset wasn't called
            if (!resetCalled) {
                setTimeout(() => {
                    
                    // Re-enable message input
                    mainInput.disabled = false;
                    mainInput.style.opacity = '';
                    mainInput.style.pointerEvents = '';
                    
                    // Hide thinking message
                    if (thinkingMessage) {
                        thinkingMessage.classList.remove('show');
                    }
                    
                    // Restore the original SVG content
                    targetBtn.innerHTML = SEND_SVG;
                    targetBtn.classList.remove('loading');
                    targetBtn.disabled = false;
                    targetBtn.style.pointerEvents = '';
                    targetBtn.style.cursor = '';

                    // Stop the loading video
                    stopLoadingVideo();
                    
                    // Clear the input field
                    mainInput.value = '';
                    if (textareaAutoResize) {
                        textareaAutoResize();
                    }

                }, 300);
            }
        }
    }

    // Add abort controller for canceling in-flight requests
    let currentAbortController = null;

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
            // Set the reset flag IMMEDIATELY
            resetCalled = true;

            // IMMEDIATELY re-enable about link (in case it was disabled)
            aboutLink.style.pointerEvents = '';
            aboutLink.style.opacity = '';
            
            // Cancel any ongoing API request
            if (currentAbortController) {
                currentAbortController.abort();
                currentAbortController = null;
            }

            // IMMEDIATELY stop loading state
            document.body.classList.remove('loading');
            
            // IMMEDIATELY reset UI elements that might be in loading state
            mainInput.disabled = false;
            mainInput.style.opacity = '';
            mainInput.style.pointerEvents = '';
            mainInput.value = '';
            if (textareaAutoResize) textareaAutoResize();
            resetSendButtons();

            // Reset rate limiting on conversation reset
            apiCallCount = 0;
            rateLimitWindowStart = Date.now();
            lastApiCall = 0;

            // IMMEDIATELY stop all videos and reset mode
            stopAllVideos();
            currentVideoMode = 'idle';
            switchingToAbout = false;

            stopSubtitleTracking();
            
            const videoControls = document.getElementById('video-controls-overlay');
            if (videoControls) {
                videoControls.style.display = 'none';
                videoControls.classList.remove('about-video-active');
            }

            const wasInAnswerView = answerView.classList.contains('active');
            if (wasInAnswerView) {
                answerView.classList.add('sucking');
            }
            
            // Reset thinking message COMPLETELY
            if (thinkingMessage) {
                thinkingMessage.classList.remove('show', 'subtitle-mode');
                thinkingMessage.textContent = 'Checking my notes';
                thinkingMessage.style.opacity = '';
            }

            // Start unzooming with a brief delay (shorter if no suction needed)
            setTimeout(() => {
                document.body.classList.add('unzooming');
            }, wasInAnswerView ? 300 : 100);
            
            // Create new abort controller for reset API call
            currentAbortController = new AbortController();
            
            // Start API reset and other cleanup in parallel
            const resetPromise = fetch('/api/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId }),
                signal: currentAbortController.signal
            }).catch(err => {
                if (err.name === 'AbortError') {
                    console.log('Reset API call was cancelled');
                } else {
                    throw err;
                }
            });
            
            // Clear saved messages
            localStorage.removeItem(`headpro_messages_${userId}`);
            
            // Reset the Head Pro container
            const headProImgContainer = document.querySelector('.head-pro-img-container');
            if (headProImgContainer) {
                headProImgContainer.classList.remove('fade-out', 'hidden');
                headProImgContainer.style.opacity = '';
                headProImgContainer.style.display = '';
            
                // Set whiskey as default and ensure it's visible but paused
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

            // Welcome message setup
            const welcomeTaglines = document.querySelectorAll('.welcome-tagline');
            const welcomePrompt = document.querySelector('.welcome-prompt');

            welcomeTaglines.forEach(tagline => {
                if (tagline) {
                    tagline.style.display = '';
                    tagline.style.opacity = '0';
                    tagline.style.transition = 'opacity 0.6s ease-out';
                }
            });

            if (welcomePrompt) {
                welcomePrompt.style.display = '';
                welcomePrompt.style.opacity = '0';
                welcomePrompt.style.transition = 'opacity 0.6s ease-out';
            }
            
            // Wait for suction animation to complete (shorter if no suction)
            await new Promise(resolve => setTimeout(resolve, wasInAnswerView ? 800 : 400));
            
            // Mark as completely sucked (only if we were in answer view)
            if (wasInAnswerView && answerView.classList.contains('active')) {
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
                
                // Ensure we're in idle mode
                currentVideoMode = 'idle';

                // Fade in welcome elements
                setTimeout(() => {
                    welcomeTaglines.forEach(tagline => {
                        if (tagline) {
                            tagline.style.opacity = '1';
                        }
                    });
                }, 300);

                setTimeout(() => {
                    if (welcomePrompt) {
                        welcomePrompt.style.opacity = '1';
                    }
                }, 300);

                // Clean up transition styles and reset flag
                setTimeout(() => {
                    welcomeTaglines.forEach(tagline => {
                        if (tagline) {
                            tagline.style.transition = '';
                            tagline.style.opacity = '';
                        }
                    });
                    if (welcomePrompt) {
                        welcomePrompt.style.transition = '';
                        welcomePrompt.style.opacity = '';
                    }
                    
                    // Clear the reset flag after everything is complete
                    resetCalled = false;
                }, 1200);

            }, 1200);
            
        } catch (error) {
            console.error('Error resetting conversation:', error);
            headProAnswer.textContent = "Couldn't reset the conversation. The Head Pro might be having technical difficulties.";
            resetCalled = false; // Clear flag on error
            currentVideoMode = 'idle';
        }
    }
    
    // Update the about link event listener
    aboutLink.addEventListener('click', (e) => {
        e.preventDefault();

        // CANCEL any ongoing API request (same as reset does)
        resetCalled = true; // Prevent response from showing
        if (currentAbortController) {
            currentAbortController.abort();
            currentAbortController = null;
        }

        // IMMEDIATELY stop loading state
        document.body.classList.remove('loading');
        
        // Reset UI elements that might be in loading state
        mainInput.disabled = false;
        mainInput.style.opacity = '';
        mainInput.style.pointerEvents = '';
        mainInput.value = '';
        if (textareaAutoResize) textareaAutoResize();
        resetSendButtons();

        // Disable logo for 3 seconds to prevent race conditions
        headProLogo.style.pointerEvents = 'none';
        setTimeout(() => {
            headProLogo.style.pointerEvents = '';
            headProLogo.style.opacity = '';
        }, 3000);
        
        // Check if we're already in about mode (video playing)
        if (aboutVideo && !aboutVideo.paused && aboutVideo.currentTime > 0) {
            // If about video is playing, restart it
            aboutVideo.currentTime = 0;
            aboutVideo.play().catch(e => console.log('About video restart failed:', e));
        } else {
            // IMMEDIATELY clear any existing thinking message content to prevent flash
            const thinkingMessage = document.getElementById('thinking-message');
            if (thinkingMessage) {
                thinkingMessage.classList.remove('show', 'subtitle-mode');
                thinkingMessage.textContent = ''; // Clear content immediately
                thinkingMessage.style.opacity = '0'; // Hide it
            }
            
            // If we're in a conversation, transition directly to about video
            if (answerView.classList.contains('active')) {
                // FIRST: Hide welcome elements immediately to prevent flashing
                const welcomeTaglines = document.querySelectorAll('.welcome-tagline');
                const welcomePrompt = document.querySelector('.welcome-prompt');
                
                // Hide welcome elements before any view switching
                welcomeTaglines.forEach(tagline => {
                    if (tagline) tagline.style.display = 'none';
                });
                if (welcomePrompt) welcomePrompt.style.display = 'none';
                
                // Then fade out the conversation content
                const userQuestion = document.getElementById('user-question');
                const headProAnswer = document.getElementById('head-pro-answer');
                const controls = document.querySelector('#answer-view .controls');
                
                // Fade out conversation elements
                if (userQuestion) userQuestion.style.opacity = '0';
                if (headProAnswer) headProAnswer.style.opacity = '0';
                if (controls) controls.style.opacity = '0';
                
                // Wait for fade-out to complete, then switch views
                setTimeout(() => {
                    // Switch to initial view (but stay zoomed)
                    initialView.classList.add('active');
                    answerView.classList.remove('active');
                    
                    // Remove conversation-started class
                    const chatContent = document.querySelector('.chat-content');
                    if (chatContent) {
                        chatContent.classList.remove('conversation-started');
                    }
                    
                    // Reset video container visibility with fade-in
                    const headProImgContainer = document.querySelector('.head-pro-img-container');
                    if (headProImgContainer) {
                        headProImgContainer.classList.remove('fade-out', 'hidden');
                        headProImgContainer.style.opacity = '0';
                        setTimeout(() => {
                            headProImgContainer.style.opacity = '1';
                        }, 100);
                    }
                    
                    // IMPORTANT: Stop any current video operations before starting about video
                    Object.values(headProVideos).forEach(video => {
                        if (video && !video.paused) {
                            video.pause();
                        }
                    });
                    
                    // Wait a moment for video operations to settle, then start about video
                    setTimeout(() => {
                        startAboutVideo();
                    }, 100);
                    
                }, 300);
            } else {
                // Starting from initial view - also hide welcome elements first
                const welcomeTaglines = document.querySelectorAll('.welcome-tagline');
                const welcomePrompt = document.querySelector('.welcome-prompt');
                
                // Hide welcome elements immediately
                welcomeTaglines.forEach(tagline => {
                    if (tagline) tagline.style.display = 'none';
                });
                if (welcomePrompt) welcomePrompt.style.display = 'none';
                
                // Stop any current video operations
                Object.values(headProVideos).forEach(video => {
                    if (video && !video.paused) {
                        video.pause();
                    }
                });
                
                // Wait a moment, then start about video
                setTimeout(() => {
                    startAboutVideo();
                }, 200);
            }
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
    
    // If no saved message, focus on main input
    if (initialView.classList.contains('active')) {
        mainInput.focus();
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
                overviewRow.innerHTML = '<td colspan="8" style="text-align: center; color: var(--ink-red);">Error loading data</td>';
            }
            
            const betHistoryTbody = document.getElementById('bet-history-tbody');
            if (betHistoryTbody) {
                betHistoryTbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--ink-red);">Error loading betting history</td></tr>';
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
            betHistoryTbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 2rem; color: var(--ink-faded); font-style: italic;">No betting history available yet.</td></tr>';
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
                    <td class="mental-score">${bet.mental_form_score}</td>
                    <td class="${outcomeClass}">${bet.outcome.toUpperCase()}</td>
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

    function startAboutVideo() {
        console.log('Starting about video experience');
        
        currentVideoMode = 'about';
        switchingToAbout = true;
        
        // Clear thinking message first
        const thinkingMessage = document.getElementById('thinking-message');
        if (thinkingMessage) {
            thinkingMessage.classList.remove('show', 'subtitle-mode');
            thinkingMessage.textContent = '';
            thinkingMessage.style.opacity = '0';
        }
        
        // Zoom animation setup (if needed)
        if (!document.body.classList.contains('zoomed') && !document.body.classList.contains('zooming')) {
            document.body.classList.add('pre-zoom');
            void document.body.offsetHeight;
            setTimeout(() => {
                document.body.classList.remove('pre-zoom');
                document.body.classList.add('zooming');
            }, 20);
            
            setTimeout(() => {
                document.body.classList.remove('zooming');
                document.body.classList.add('zoomed');
            }, 3000);
        }
        
        // SEAMLESS TRANSITION: Prepare about video while current video is still showing
        if (aboutVideo) {
            // Prepare the about video (but don't show it yet)
            aboutVideo.currentTime = 0;
            aboutVideo.muted = true;
            currentSubtitleIndex = -1;
            
            // Load the video to the first frame if it's not already loaded
            aboutVideo.load();
            
            // Wait for it to be ready, then do the switch
            const handleCanPlay = () => {
                aboutVideo.removeEventListener('canplay', handleCanPlay);
                
                // NOW do the instant switch
                // Hide all other videos first
                Object.values(headProVideos).forEach(video => {
                    if (video && video !== aboutVideo) {
                        video.style.display = 'none';
                        video.pause();
                    }
                });
                
                // Immediately show about video
                aboutVideo.style.display = 'block';
                
                // Set up video controls
                const videoControls = document.getElementById('video-controls-overlay');
                if (videoControls) {
                    videoControls.style.display = 'block';
                    videoControls.classList.add('about-video-active');
                }
                
                // Set up event handlers
                setupAboutVideoHandlers();
                
                // Show subtitle area
                const subtitleElement = document.getElementById('thinking-message');
                if (subtitleElement) {
                    subtitleElement.classList.add('show', 'subtitle-mode');
                    subtitleElement.style.opacity = '1';
                    subtitleElement.textContent = '';
                }
                
                // Start playing
                aboutVideo.play().then(() => {
                    startSubtitleTracking();
                }).catch(e => {
                    console.error("About video play failed:", e);
                });
                
                switchingToAbout = false;
            };
            
            // If the video is already ready, execute immediately
            if (aboutVideo.readyState >= 3) { // HAVE_FUTURE_DATA or higher
                handleCanPlay();
            } else {
                // Otherwise wait for it to be ready
                aboutVideo.addEventListener('canplay', handleCanPlay);
                
                // Fallback timeout in case canplay doesn't fire
                setTimeout(handleCanPlay, 100);
            }
        }
    }

    function setupAboutVideoHandlers() {
        // Video click handler
        aboutVideo.onclick = function() {
            if (aboutVideo.paused) {
                aboutVideo.play().catch(e => console.log('Video resume failed:', e));
            } else {
                aboutVideo.pause();
            }
        };
        
        // Update mute button
        updateMuteButton();

        const muteBtn = document.getElementById('about-mute-btn');
        if (muteBtn) {
            muteBtn.onclick = function(e) {
                e.stopPropagation();
                toggleAboutVideoSound();
            };
        }
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
        console.log('Cleaning up about video');
        
        // Only proceed if we're actually in about mode
        if (currentVideoMode !== 'about') {
            return;
        }
        
        stopSubtitleTracking();

        // PROPERLY reset the thinking message element back to normal state
        const thinkingMessage = document.getElementById('thinking-message');
        if (thinkingMessage) {
            // Remove all about-related classes and content
            thinkingMessage.classList.remove('show', 'subtitle-mode');
            thinkingMessage.textContent = 'Checking my notes'; // Reset to default thinking text
            thinkingMessage.style.opacity = ''; // Clear any inline opacity
            thinkingMessage.style.display = ''; // Clear any inline display
            
            console.log('Reset thinking message to normal state');
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

        currentVideoMode = 'idle';
    
        // Only start loading video if NOT during a reset
        if (!document.body.classList.contains('unzooming')) {
            // Mark conversation as started since they're sending a real message
            const chatContent = document.querySelector('.chat-content');
            if (chatContent) {
                chatContent.classList.add('conversation-started');
            }
            
            // Start loading video for the next response
            setTimeout(() => {
                startLoadingVideo();
            }, 500);
        }
    }

    // Get the logo element
    const headProLogo = document.querySelector('.head-pro-logo');

    // Add click event listener to the logo
    if (headProLogo) {
        headProLogo.addEventListener('click', (e) => {
            e.preventDefault();

            // Disable logo for 1 second
            headProLogo.style.pointerEvents = 'none';
            headProLogo.style.opacity = '0.5';
            setTimeout(() => {
                headProLogo.style.pointerEvents = '';
                headProLogo.style.opacity = '';
            }, 1000);
            
            // If we're in About video mode, just clean that up and return to initial view
            if (currentVideoMode === 'about' || (aboutVideo && aboutVideo.style.display !== 'none')) {
                // Stop the about video immediately
                if (aboutVideo) {
                    aboutVideo.pause();
                    aboutVideo.style.display = 'none';
                }
                
                // Nuclear option: immediately clear everything about thinking message
                const thinkingMessage = document.getElementById('thinking-message');
                if (thinkingMessage) {
                    thinkingMessage.style.display = 'none';
                    thinkingMessage.className = 'thinking-message'; // Reset to base class only
                    thinkingMessage.textContent = ''; // Clear text immediately
                    thinkingMessage.style.opacity = '0';
                }
                
                // Stop subtitle interval
                if (subtitleInterval) {
                    clearInterval(subtitleInterval);
                    subtitleInterval = null;
                }
                currentSubtitleIndex = -1;
                
                // Reset thinking message to normal state after everything settles
                setTimeout(() => {
                    if (thinkingMessage) {
                        thinkingMessage.textContent = 'Checking my notes';
                        thinkingMessage.style.cssText = ''; // This should clear display: none
                        thinkingMessage.style.display = ''; // But let's be explicit about it
                    }
                }, 200);
                
                // Hide video controls
                const videoControls = document.getElementById('video-controls-overlay');
                if (videoControls) {
                    videoControls.style.display = 'none';
                }
                
                // Reset video mode
                currentVideoMode = 'idle';
                
                // Simple unzoom if needed
                if (document.body.classList.contains('zoomed') || document.body.classList.contains('zooming')) {
                    document.body.classList.remove('zoomed', 'zooming');
                    document.body.classList.add('unzooming');
                    setTimeout(() => {
                        document.body.classList.remove('unzooming');
                    }, 1000);
                }
                
                // Reset to default video (whiskey)
                Object.values(headProVideos).forEach(video => {
                    if (video) video.style.display = 'none';
                });
                currentVideo = headProVideos.whiskey;
                if (currentVideo) {
                    currentVideo.style.display = 'block';
                    currentVideo.currentTime = 0;
                }
                
                // FIXED: Set up welcome text with proper fade-in (same as resetConversation)
                const welcomeTaglines = document.querySelectorAll('.welcome-tagline');
                const welcomePrompt = document.querySelector('.welcome-prompt');
                
                // Prepare welcome elements with fade-in
                welcomeTaglines.forEach(tagline => {
                    if (tagline) {
                        tagline.style.display = ''; // Reset display
                        tagline.style.opacity = '0'; // Start invisible
                        tagline.style.transition = 'opacity 0.6s ease-out'; // Add smooth transition
                    }
                });
                
                if (welcomePrompt) {
                    welcomePrompt.style.display = ''; // Reset display
                    welcomePrompt.style.opacity = '0'; // Start invisible
                    welcomePrompt.style.transition = 'opacity 0.6s ease-out'; // Add smooth transition
                }
                
                // Fade in welcome elements with timing similar to resetConversation
                setTimeout(() => {
                    welcomeTaglines.forEach(tagline => {
                        if (tagline) {
                            tagline.style.opacity = '1';
                        }
                    });
                }, 400); // Start fading during unzoom
                
                setTimeout(() => {
                    if (welcomePrompt) {
                        welcomePrompt.style.opacity = '1';
                    }
                }, 400); // Fade in prompt later
                
                // Clean up transition styles
                setTimeout(() => {
                    welcomeTaglines.forEach(tagline => {
                        if (tagline) {
                            tagline.style.transition = '';
                            tagline.style.opacity = '';
                        }
                    });
                    if (welcomePrompt) {
                        welcomePrompt.style.transition = '';
                        welcomePrompt.style.opacity = '';
                    }
                }, 1800);
                
                return; // Don't do anything else
            }
            
            // If we're in a conversation, do the full reset
            if (answerView.classList.contains('active') || document.body.classList.contains('loading')) {
                resetConversation();
            }
            
            // Otherwise, do nothing (don't interrupt users on fresh initial screen)
        });
        
        // Make it look clickable
        headProLogo.style.cursor = 'pointer';
    }

    mainSendBtn.addEventListener('click', () => {
        const isInitial = initialView.classList.contains('active');
        sendMessage(mainInput.value, isInitial);
    });

    mainInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const isInitial = initialView.classList.contains('active');
            sendMessage(mainInput.value, isInitial);
        }
    });

    function setupTextareaAutoResize() {
        const textarea = document.getElementById('main-input');
        if (!textarea) return null;
        
        // Auto-resize function
        function autoResize() {
            // Reset to a minimal height first
            textarea.style.height = 'auto';
            
            // Get the scroll height (content height)
            const scrollHeight = textarea.scrollHeight;
            
            // Calculate min and max heights in pixels
            const style = window.getComputedStyle(textarea);
            const fontSize = parseFloat(style.fontSize);
            const minHeight = fontSize * 3.2; // 3.2em in pixels
            const maxHeight = fontSize * 8;   // 8em in pixels
            
            // Set the appropriate height
            if (scrollHeight <= minHeight) {
                textarea.style.height = minHeight + 'px';
                textarea.style.overflowY = 'hidden';
            } else if (scrollHeight <= maxHeight) {
                textarea.style.height = scrollHeight + 'px';
                textarea.style.overflowY = 'hidden';
            } else {
                textarea.style.height = maxHeight + 'px';
                textarea.style.overflowY = 'auto';
            }
        }
        
        // Add event listeners
        textarea.addEventListener('input', autoResize);
        textarea.addEventListener('paste', () => setTimeout(autoResize, 0));
        textarea.addEventListener('cut', () => setTimeout(autoResize, 0));
        
        // Handle Enter key
        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                if (e.shiftKey) {
                    // Allow new line on Shift+Enter
                    setTimeout(autoResize, 0);
                    return;
                } else {
                    // Submit on Enter
                    e.preventDefault();
                    const isInitial = initialView.classList.contains('active');
                    sendMessage(textarea.value, isInitial);
                }
            }
        });
        
        // Call once to set initial size
        autoResize();
        
        // Return the autoResize function so it can be called externally
        return autoResize;
    }

    setupTextareaAutoResize();
    

});