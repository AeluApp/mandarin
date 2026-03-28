/// <reference types="@capacitor/splash-screen" />

import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.aelu.app',
  appName: 'Aelu',
  webDir: 'mandarin/web/static',

  server: {
    // In development, proxy to the Flask backend.
    // Set CAPACITOR_DEV=1 before running to enable.
    url: process.env.CAPACITOR_DEV ? 'http://localhost:5000' : undefined,
    cleartext: !!process.env.CAPACITOR_DEV,
  },

  ios: {
    contentInset: 'automatic',
    backgroundColor: '#F2EBE0',
    preferredContentMode: 'mobile',
  },

  android: {
    backgroundColor: '#F2EBE0',
    allowMixedContent: false,
  },

  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      launchAutoHide: true,
      launchFadeOutDuration: 300,
      backgroundColor: '#F2EBE0', // --color-base (light mode)
      showSpinner: false,
      splashFullScreen: false,
      splashImmersive: false,
    },
    StatusBar: {
      style: 'LIGHT', // Dark text on light background (matches Civic Sanctuary aesthetic)
      backgroundColor: '#F2EBE0',
    },
    Keyboard: {
      resize: 'body',
      resizeOnFullScreen: true,
    },
  },
};

export default config;
