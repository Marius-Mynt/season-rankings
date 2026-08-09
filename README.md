# 🎮 Smash Tournament Season Rankings

A web app for tracking and analyzing Smash tournament results using Start.gg data.

## Features

- **📤 Easy Import**: Just paste a Start.gg tournament URL
- **🏆 Season Rankings**: Automatic point calculation across all tournaments
- **⚙️ Customizable Points**: Adjust the scoring system to your community's rules
- **📊 Attendance Scaling**: Bigger tournaments can award more points
- **🥊 Head-to-Head**: Look up any player matchup
- **📥 Excel Export**: Download rankings for sharing

## Quick Setup (10 minutes)

### Step 1: Get Your Start.gg API Key

1. Go to [start.gg/admin/profile/developer](https://start.gg/admin/profile/developer)
2. Click "Create new token"
3. Copy your API key (save it somewhere safe!)

### Step 2: Create GitHub Repository

1. Go to [github.com](https://github.com) and sign in (or create account)
2. Click the green **"New"** button to create a new repository
3. Name it something like `season-rankings`
4. Make it **Public** (required for free Streamlit hosting)
5. Click **"Create repository"**

### Step 3: Upload the App Files

Upload these files to your new repository:
- `streamlit_app.py`
- `requirements.txt`
- `.streamlit/config.toml`
- `.gitignore`

You can do this by clicking **"uploading an existing file"** on your new repo page.

### Step 4: Deploy on Streamlit Cloud

1. Go to [streamlit.io/cloud](https://streamlit.io/cloud)
2. Click **"Sign in"** and connect your GitHub account
3. Click **"New app"**
4. Select your repository and `streamlit_app.py`
5. Click **"Deploy"**

### Step 5: Add Your API Key

1. In Streamlit Cloud, go to your app's **Settings** (⚙️ icon)
2. Click **"Secrets"**
3. Add this (replace with your actual key):
   ```toml
   STARTGG_API_KEY = "your_api_key_here"
   ```
4. Click **"Save"**

### Step 6: Done! 🎉

Your app is now live at `https://your-app-name.streamlit.app`!

## Using the App

### Adding Tournaments

1. Click **"➕ Add Tournament"** in the sidebar
2. Paste the Start.gg tournament URL
3. Click **"Add Tournament"**
4. Wait for import to complete

### Adjusting Rankings

1. Click **"⚙️ Settings"** in the sidebar
2. Modify point values for each placement
3. Enable/disable options:
   - **Attendance Scaling**: Larger tournaments = more points
   - **Best N Tournaments**: Only count top results
   - **Drop Worst**: Exclude worst result
   - **Min. Tournaments**: Require X events to qualify
4. Click **"Save Settings"**

### Head-to-Head

1. Click **"🥊 Head-to-Head"** in the sidebar
2. Select two players
3. See their record and match history

## Customization

### Change Colors

Edit `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#FF6B6B"      # Accent color
backgroundColor = "#0E1117"    # Main background
secondaryBackgroundColor = "#262730"  # Sidebar/cards
textColor = "#FAFAFA"          # Text color
```

### Add Your Logo

In `streamlit_app.py`, add at the top of `main()`:

```python
st.image("your_logo.png", width=200)
```

## Troubleshooting

### "API key not configured"
Make sure you added `STARTGG_API_KEY` in Streamlit Cloud → Settings → Secrets

### "Could not extract tournament slug"
Make sure the URL is a valid Start.gg tournament URL, like:
`https://www.start.gg/tournament/your-tournament/events`

### Import takes too long
Large tournaments with 100+ entrants take longer. The app shows progress.

## Support

Questions? Issues? Create an issue on GitHub or reach out to your community TO!

---

Built with ❤️ for the Smash community
