#!/usr/bin/env python3
"""
Simple UI Test - Just to verify the download button is visible
No Spotify API calls, no downloads, just pure UI testing
"""

import customtkinter as ctk

class TestApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Large window for macOS
        self.title("🎵 Download Button Test")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        
        # Dark theme
        ctk.set_appearance_mode("dark")
        
        # Colors
        self.colors = {
            "primary": "#8B5CF6",
            "secondary": "#06B6D4", 
            "accent": "#F59E0B",
            "surface": "#1F2937",
            "glass": "#2D1B69",
            "glass_border": "#4C1D95",
            "success": "#10B981",
            "text_primary": "#F9FAFB",
            "background": "#0F0F23"
        }
        
        self.configure(fg_color=self.colors["background"])
        
        # Create UI
        self.create_test_ui()
    
    def create_test_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=80, corner_radius=0, fg_color=self.colors["primary"])
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        
        title = ctk.CTkLabel(header, text="🎵 Download Button Visibility Test", 
                           font=ctk.CTkFont(size=28, weight="bold"),
                           text_color=self.colors["text_primary"])
        title.pack(pady=20)
        
        # Main content (scrollable)
        main_frame = ctk.CTkScrollableFrame(self, corner_radius=20, fg_color=self.colors["surface"])
        main_frame.pack(padx=30, pady=20, fill="both", expand=True)
        
        # Test sections
        for i in range(3):
            section = ctk.CTkFrame(main_frame, corner_radius=15, fg_color=self.colors["glass"], 
                                 border_width=2, border_color=self.colors["glass_border"])
            section.pack(fill="x", padx=20, pady=10)
            
            label = ctk.CTkLabel(section, text=f"📋 Test Section {i+1}", 
                               font=ctk.CTkFont(size=18, weight="bold"))
            label.pack(pady=15)
            
            content = ctk.CTkTextbox(section, height=100, corner_radius=10)
            content.pack(fill="x", padx=20, pady=(0, 15))
            content.insert("0.0", f"This is test section {i+1}\nWith some sample content\nTo fill space and test scrolling")
            content.configure(state="disabled")
        
        # THE IMPORTANT PART - Download Control Center
        controls_card = ctk.CTkFrame(main_frame, corner_radius=20, fg_color=self.colors["glass"],
                                   border_width=3, border_color=self.colors["accent"])  # Extra visible border
        controls_card.pack(fill="x", padx=20, pady=20)
        
        # Big obvious title
        title_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        controls_title = ctk.CTkLabel(title_frame, text="🎛️ DOWNLOAD CONTROL CENTER", 
                                    font=ctk.CTkFont(size=24, weight="bold"),
                                    text_color=self.colors["accent"])  # Bright color
        controls_title.pack(side="left")
        
        indicator = ctk.CTkLabel(title_frame, text="👈 LOOK HERE!", 
                               font=ctk.CTkFont(size=16, weight="bold"),
                               text_color=self.colors["accent"])
        indicator.pack(side="right")
        
        # Button row
        button_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        button_frame.pack(fill="x", padx=25, pady=(0, 25))
        
        # BIG OBVIOUS DOWNLOAD BUTTON
        self.download_btn = ctk.CTkButton(button_frame, text="▶️ START DOWNLOAD", 
                                        width=250, height=60, corner_radius=20,
                                        fg_color=self.colors["success"], 
                                        hover_color="#059669",
                                        font=ctk.CTkFont(size=20, weight="bold"),
                                        command=self.test_download)
        self.download_btn.pack(side="left", padx=(0, 20))
        
        # Stop button
        self.stop_btn = ctk.CTkButton(button_frame, text="⏹️ STOP", 
                                    width=150, height=60, corner_radius=20,
                                    fg_color="#DC2626", hover_color="#B91C1C",
                                    font=ctk.CTkFont(size=20, weight="bold"),
                                    command=self.test_stop)
        self.stop_btn.pack(side="left")
        
        # Status
        self.status_label = ctk.CTkLabel(button_frame, text="🟢 BUTTONS ARE VISIBLE!", 
                                       font=ctk.CTkFont(size=16, weight="bold"),
                                       text_color=self.colors["success"])
        self.status_label.pack(side="right", padx=20)
        
        # Bottom spacing
        spacer = ctk.CTkFrame(main_frame, height=50, fg_color="transparent")
        spacer.pack(fill="x")
        
        print("✅ TEST UI CREATED")
        print("🎛️ Download Control Center should be visible")
        print("▶️ Look for the START DOWNLOAD button")
    
    def test_download(self):
        self.status_label.configure(text="🚀 DOWNLOAD BUTTON CLICKED!", text_color=self.colors["accent"])
        self.download_btn.configure(text="✅ BUTTON WORKS!")
        print("✅ DOWNLOAD BUTTON CLICKED - IT'S WORKING!")
    
    def test_stop(self):
        self.status_label.configure(text="⏹️ STOP BUTTON CLICKED!", text_color="#DC2626")
        self.stop_btn.configure(text="✅ STOP WORKS!")
        print("✅ STOP BUTTON CLICKED - IT'S WORKING!")

if __name__ == "__main__":
    print("🧪 Starting UI Test...")
    print("📱 This will show ONLY the UI without any Spotify/YouTube calls")
    print("🎯 Look for the bright 'DOWNLOAD CONTROL CENTER' section")
    
    app = TestApp()
    app.mainloop()