// import dedent from 'ts-dedent';
import { App } from "cdkactions";
import { PyPIPublishStack } from "@pennlabs/kraken";

const app = new App();
new PyPIPublishStack(app);

app.synth();
