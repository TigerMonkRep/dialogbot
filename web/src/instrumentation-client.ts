import { analytics } from '@heycatch/sdk';

// HeyCatch analytics. Next runs this file on the client before hydration, so every page is tracked.
analytics.init({
  projectKey: 'hck_pk_90favo26Buk7jLZfyfJGIWUGwELPWgMK',
  install: {
    framework: 'nextjs',
    frameworkVersion: '16',
    agent: 'claude-code',
  },
});
