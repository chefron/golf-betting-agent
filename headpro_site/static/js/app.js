document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const messagesDiv = document.getElementById('messages');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const resetBtn = document.getElementById('reset-btn');
    const aboutLink = document.getElementById('about-link');
    const aboutModal = document.getElementById('about-modal');
    const closeModal = document.querySelector('.close');
    const welcomeMessage = document.querySelector('.welcome-message');
    
    // Generate/retrieve user ID
    const userId = localStorage.getItem('userId') || 
        `user_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
    localStorage.setItem('userId', userId);
    
    // Load previous messages from localStorage
    function loadMessages() {
        const savedMessages = localStorage.getItem(`headpro_messages_${userId}`);
        
        if (savedMessages) {
            try {
                const messages = JSON.parse(savedMessages);
                if (messages && messages.length > 0) {
                    // If we have saved messages, hide welcome message
                    welcomeMessage.style.display = 'none';
                    
                    messages.forEach(msg => {
                        addMessage(msg.text, msg.sender, false, false);
                    });
                    
                    // Auto-scroll to bottom
                    messagesDiv.scrollTop = messagesDiv.scrollHeight;
                }
            } catch (e) {
                console.error('Error loading saved messages:', e);
                // Clear corrupt data
                localStorage.removeItem(`headpro_messages_${userId}`);
            }
        }
    }
    
    // Save messages to localStorage
    function saveMessages() {
        const messageElements = messagesDiv.querySelectorAll('.message:not(.typing)');
        const messages = Array.from(messageElements).map(el => ({
            text: el.textContent,
            sender: el.classList.contains('user') ? 'user' : 'assistant'
        }));
        
        localStorage.setItem(`headpro_messages_${userId}`, JSON.stringify(messages));
    }
    
    // Add a message to the chat
    function addMessage(text, sender, isTyping = false, save = true) {
        // Hide welcome message when first message is added
        if (welcomeMessage.style.display !== 'none') {
            welcomeMessage.style.display = 'none';
        }
        
        const messageDiv = document.createElement('div');
        const id = `msg-${Date.now()}`;
        messageDiv.id = id;
        messageDiv.className = `message ${sender} ${isTyping ? 'typing' : ''}`;
        
        if (isTyping) {
            // Create typing indicator
            const typingIndicator = document.createElement('div');
            typingIndicator.className = 'typing-indicator';
            typingIndicator.innerHTML = '<span></span><span></span><span></span>';
            messageDiv.appendChild(typingIndicator);
        } else {
            messageDiv.textContent = text;
        }
        
        messagesDiv.appendChild(messageDiv);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        
        // Save messages to localStorage (if not a typing indicator)
        if (save && !isTyping) {
            saveMessages();
        }
        
        return id;
    }
    
    // Send message to API
    async function sendMessage() {
        const message = messageInput.value.trim();
        if (!message) return;
        
        // Add user message
        addMessage(message, 'user');
        messageInput.value = '';
        
        // Show typing indicator
        const typingId = addMessage('', 'assistant', true, false);
        
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
            
            // Remove typing indicator
            document.getElementById(typingId)?.remove();
            
            // Add Head Pro response
            addMessage(data.response, 'assistant');
        } catch (error) {
            console.error('Error sending message:', error);
            
            // Remove typing indicator
            document.getElementById(typingId)?.remove();
            
            // Add error message
            addMessage("The Head Pro seems to have wandered off to the 19th hole. Try again in a moment.", 'assistant');
        }
    }
    
    // Reset conversation
    async function resetConversation() {
        try {
            // Send reset request to API
            await fetch('/api/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId })
            });
            
            // Clear messages from UI
            messagesDiv.innerHTML = '';
            
            // Clear saved messages
            localStorage.removeItem(`headpro_messages_${userId}`);
            
            // Show welcome message
            welcomeMessage.style.display = 'block';
        } catch (error) {
            console.error('Error resetting conversation:', error);
            addMessage("Couldn't reset the conversation. The Head Pro might be having technical difficulties.", 'assistant');
        }
    }
    
    // Event Listeners
    sendBtn.addEventListener('click', sendMessage);
    
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
    
    resetBtn.addEventListener('click', resetConversation);
    
    // Modal controls
    aboutLink.addEventListener('click', (e) => {
        e.preventDefault();
        aboutModal.style.display = 'block';
    });
    
    closeModal.addEventListener('click', () => {
        aboutModal.style.display = 'none';
    });
    
    window.addEventListener('click', (e) => {
        if (e.target === aboutModal) {
            aboutModal.style.display = 'none';
        }
    });
    
    // Initialize
    loadMessages();
    messageInput.focus();
});