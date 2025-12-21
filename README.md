# Philips Pet Series Integration

This is a Home Assistant integration for the Philips Pet Series devices. It allows you to control and monitor various aspects of your Philips Pet Series devices through Home Assistant.

## Features


<img width="323" alt="Screenshot 2024-10-11 at 17 43 06" src="https://github.com/user-attachments/assets/2a7b5536-1952-40d3-8bea-b214e145f9d3">
<img width="326" alt="Screenshot 2024-10-11 at 17 43 25" src="https://github.com/user-attachments/assets/fe4101cd-f250-4f45-8af6-bcec2c8b77b4">
<img width="329" alt="Screenshot 2024-10-11 at 17 42 48" src="https://github.com/user-attachments/assets/eed2888f-101f-473c-a706-47409116e1ef">

> [!NOTE]
> Camera support is not yet implemented.

## Installation

This integration can be installed via [HACS](https://hacs.xyz/).

1. Ensure that [HACS](https://hacs.xyz/) is installed and configured in your Home Assistant setup.
2. Add this repository to HACS:
   - Go to HACS in the Home Assistant sidebar.
   - Click on the three dots in the top right corner and select "Custom repositories".
   - Add the repository URL: `https://github.com/abovecolin/HA-Philips-Pet-Series` and select the category as "Integration".
3. Search for "Philips Pet Series" in HACS and install it.
4. Restart Home Assistant.

## Configuration

1. Go to the Home Assistant Configuration page.
2. Click on "Integrations".
3. Click on the "+" button to add a new integration.
4. Search for "Philips Pet Series" and follow the setup instructions.

## Authentication

This integration uses OAuth2 tokens (an Access Token and Refresh Token) to authenticate with the PetsSeries API. Follow the steps below to obtain and set up your tokens.

### Obtaining Tokens

1. **Login via Web Interface**: 
 - Navigate to [PetsSeries Appliance Login](https://www.home.id/find-appliance).
    - Select a PetsSeries product (Search for "PAW"), click on "register your device" and log in with your credentials.

> [!TIP]
> If you have not registered your device yet, you can do this through either the PhilipsPetSeries app(s) or find your device on the [Philips Home Support](https://www.home.id/support) page and register it with a new account.

2. **Retrieve Tokens**:
    - After logging in, you will be redirected to your account dashboard.
    - Open your browser's developer tools (usually by pressing F12 or Ctrl+Shift+I).
    - Go to the Application tab and inspect the cookies.
    - Locate and copy the values from the `cc-access-token` and `cc-refresh-token` field from the cookies.

3. **Provide Tokens to the Integration**:
    - You can provide the `access_token` and `refresh_token` when setting up the integration.

After the first run, the tokens will be saved automatically, and you won't need to provide them again unless they are invalidated.

## Extra Functionality (Optional)

For the following extra functionalities:
- Configuration of settings for the camera
- The functionality to send a feed command
- Set the portion size

Some additional steps are required. Unfortunately, a better approach hasn’t been found yet. Here’s what is needed:

### Required Information:
- **Pet Feeder Client ID**: This can be found in the PetsSeries app's device screen.
  - Navigate to: **App Home Screen > Your Pet Feeder > Settings > Device ID**.
- **Pet Feeder IP Address**: The IP address of the device.
- **Pet Feeder Local Key**: See below for extraction instructions.

### Extracting the Local Key:
Obtaining the Local Key requires some additional effort. You can extract it using Frida on a rooted Android device to intercept the localKey at runtime.

#### Method 1: Frida Interception (Recommended for Advanced Users)

**Prerequisites:**
- A rooted Android device
- USB debugging enabled
- Frida installed on your computer and Frida server on your Android device

**Recommended Tool:**
Use the [MagiskFrida](https://github.com/AeonLucid/MagiskFrida) module to auto-start Frida on boot, or manually install Frida server on your rooted Android device.

**Extraction Steps:**

1. **Connect your Android device** via USB and ensure USB debugging is enabled.

2. **Install Frida server** on your Android device (if not using MagiskFrida):
   ```bash
   # Download frida-server for your Android architecture
   # Push to device and run:
   adb push frida-server /data/local/tmp/
   adb shell "chmod 755 /data/local/tmp/frida-server"
   adb shell "/data/local/tmp/frida-server &"
   ```

3. **Run Frida trace** to intercept method calls:
   ```bash
   frida-trace -U --decorate \
     -j '*!*encodeString*' \
     -f com.versuni.nbx.petsseries \
     -o output.txt
   ```

4. **Open the Philips Pet Series app** on your Android device and navigate to your pet feeder device. This will trigger the app to load device information including the localKey.

5. **Search for localKey** in the `output.txt` file:
   ```bash
   grep -i "localkey" output.txt
   ```
   
   You'll find a line like:
   ```json
   "localKey":"FceXXX]+$7}9Zl."
   ```
   
   The value between the quotes (e.g., `FceXXX]+$7}9Zl.`) is your Local Key.

**Note:** The Frida trace will capture various method calls. The localKey typically appears in JSON responses or encoded strings. Look for patterns like `"localKey":` or `localKey=` in the output.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request on the [GitHub repository](https://github.com/abovecolin/HA-Philips-Pet-Series).

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
