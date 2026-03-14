import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.aelu.app',
  appName: 'Aelu',
  webDir: '../mandarin/web/static',
  server: {
    url: process.env.CAPACITOR_SERVER_URL || 'http://localhost:5173/?native=1',
    cleartext: true,
  },
  ios: {
    scheme: 'Aelu',
    contentInset: 'automatic',
  },
  android: {
    allowMixedContent: false,
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      backgroundColor: '#F2EBE0',
      showSpinner: false,
      launchAutoHide: true,
    },
    StatusBar: {
      style: 'LIGHT',
      backgroundColor: '#F2EBE0',
    },
    Keyboard: {
      resize: 'body',
      resizeOnFullScreen: true,
    },
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
};

export default config;
