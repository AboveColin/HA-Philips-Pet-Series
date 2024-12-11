# Philips Pet Series Integration

This is a Home Assistant integration for the Philips Pet Series devices. It allows you to control and monitor various aspects of your Philips Pet Series devices through Home Assistant.

## Features

- **Switches**: Control various switches on your Philips Pet Series devices.
- **Sensors**: Monitor different sensors, including event sensors and Tuya status sensors.
- **Numbers**: Adjust numerical settings like portion sizes.
- **Calendars**: View meal schedules.

**Note**: Camera support is not yet implemented.

<img width="323" alt="Screenshot 2024-10-11 at 17 43 06" src="https://github.com/user-attachments/assets/2a7b5536-1952-40d3-8bea-b214e145f9d3">
<img width="326" alt="Screenshot 2024-10-11 at 17 43 25" src="https://github.com/user-attachments/assets/fe4101cd-f250-4f45-8af6-bcec2c8b77b4">
<img width="329" alt="Screenshot 2024-10-11 at 17 42 48" src="https://github.com/user-attachments/assets/eed2888f-101f-473c-a706-47409116e1ef">

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

This integration uses OAuth2 tokens (access_token and refresh_token) to authenticate with the PetsSeries API. Follow the steps below to obtain and set up your tokens.

### Obtaining Tokens

1. **Login via Web Interface**:
    - Navigate to [PetsSeries Appliance Login](https://www.home.id/find-appliance).
    - Select a PetsSeries product (Search for "PAW"), click on "register your device" and log in with your credentials.

2. **Retrieve Tokens**:
    - After logging in, you will be redirected to a "Thanks for your purchase" screen.
    - Open your browser's developer tools (usually by pressing F12 or Ctrl+Shift+I).
    - Go to the Application tab and inspect the cookies.
    - Locate and copy the values from the `cc-access-token` and `cc-refresh-token` feild from the cookies.

3. **Provide Tokens to the Integration**:
    - You can provide the `access_token` and `refresh_token` when setting up the integration.

After the first run, the tokens will be saved automatically, and you won't need to provide them again unless they are invalidated.

## Tuya Integration (Optional)

The integration also supports Tuya devices, which is required for controlling features such as food dispensers. To enable this, you will need to provide the following:

- **client_id**: This can be found in the PetsSeries app's device screen.
- **ip**: The IP address of the device.
- **local_key**: You can extract this from the device using a rooted phone and running frida-trace as shown below:
    
```bash 
frida-trace -H 127.0.0.1:27042 --decorate -j '*!*encodeString*' -f com.versuni.petsseries -o <a folder location to save frida_trace outputs to a local file>
```
Then, search for the localKey in the logs.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request on the [GitHub repository](https://github.com/abovecolin/HA-Philips-Pet-Series).

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
