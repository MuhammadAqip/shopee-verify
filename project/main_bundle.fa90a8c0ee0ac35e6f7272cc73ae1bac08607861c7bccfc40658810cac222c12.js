(function () {
    'use strict';

    function registerCollector(collector) {
        try {
            if (typeof window === "undefined")
                return;
            var root = window;
            if (!root.__DYNAMIC_COLLECTOR__ || typeof root.__DYNAMIC_COLLECTOR__.register !== "function") {
                return;
            }
            root.__DYNAMIC_COLLECTOR__.register(collector);
        }
        catch (_error) {
            // Dynamic artifacts are loaded into an application page. Registration is
            // best effort and must never create an uncaught page-level exception.
        }
    }

    var WEBGL_WIDTH = 32;
    var WEBGL_HEIGHT = 32;
    var MAX_RENDERER_INFO_LENGTH = 512;
    var CONTEXT_OPTIONS = {
        alpha: false,
        antialias: false,
        depth: false,
        stencil: false,
        preserveDrawingBuffer: false,
    };
    var RED_VERTEX_SHADER = [
        "attribute vec2 aPosition;",
        "void main(void) {",
        "  gl_Position = vec4(aPosition, 0.0, 1.0);",
        "}",
    ].join("\n");
    var SOLID_RED_FRAGMENT_SHADER = [
        "precision mediump float;",
        "void main(void) {",
        "  gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0);",
        "}",
    ].join("\n");
    var TEXTURE_VERTEX_SHADER = [
        "attribute vec2 aPosition;",
        "attribute vec2 aTexCoord;",
        "varying vec2 vTexCoord;",
        "void main(void) {",
        "  gl_Position = vec4(aPosition, 0.0, 1.0);",
        "  vTexCoord = aTexCoord;",
        "}",
    ].join("\n");
    var TEXTURE_FRAGMENT_SHADER = [
        "precision mediump float;",
        "uniform sampler2D uTexture;",
        "varying vec2 vTexCoord;",
        "void main(void) {",
        "  gl_FragColor = texture2D(uTexture, vTexCoord);",
        "}",
    ].join("\n");
    var RED_RECT_POSITIONS = new Float32Array([
        -0.75, -0.75,
        0.75, -0.75,
        -0.75, 0.75,
        0.75, 0.75,
    ]);
    var TRIANGLE_POSITIONS = new Float32Array([
        0.0, 0.75,
        -0.75, -0.75,
        0.75, -0.75,
    ]);
    var QUAD_POSITIONS = new Float32Array([
        -1, -1,
        1.0, -1,
        -1, 1.0,
        1.0, 1.0,
    ]);
    var QUAD_TEX_COORDS = new Float32Array([
        0.0, 0.0,
        1.0, 0.0,
        0.0, 1.0,
        1.0, 1.0,
    ]);
    var CHECKER_TEXTURE = new Uint8Array([
        255, 255, 255, 255, 0, 0, 0, 255, 255, 255, 255, 255, 0, 0, 0, 255,
        0, 0, 0, 255, 255, 255, 255, 255, 0, 0, 0, 255, 255, 255, 255, 255,
        255, 255, 255, 255, 0, 0, 0, 255, 255, 255, 255, 255, 0, 0, 0, 255,
        0, 0, 0, 255, 255, 255, 255, 255, 0, 0, 0, 255, 255, 255, 255, 255,
    ]);
    function emptySample() {
        return { supported: false, version: null, hash: null };
    }
    function safeString(value) {
        if (value === null || value === undefined)
            return null;
        try {
            return String(value);
        }
        catch (_error) {
            return null;
        }
    }
    function normalizeVersion(value) {
        if (!value)
            return null;
        return value.indexOf("WebGL 1.0") === 0 ? "WebGL 1.0" : value;
    }
    // Shared by separately bundled SDK and Dynamic copies in the same document.
    function contextState() {
        if (typeof document === "undefined")
            return null;
        try {
            var owner = document;
            if (!owner.__dynamicCollectWebGLContextV1__) {
                Object.defineProperty(owner, "__dynamicCollectWebGLContextV1__", {
                    value: { context: null, busy: false, disabled: false },
                });
            }
            return owner.__dynamicCollectWebGLContextV1__ || null;
        }
        catch (_error) {
            // Without a shared owner, do not create unbounded per-bundle fallbacks.
            return null;
        }
    }
    function acquireContext() {
        var state = contextState();
        if (!state || state.busy || state.disabled)
            return null;
        state.busy = true;
        try {
            if (state.context) {
                if (state.context.gl.isContextLost()) {
                    state.disabled = true;
                    state.busy = false;
                    return null;
                }
                state.context.canvas.width = WEBGL_WIDTH;
                state.context.canvas.height = WEBGL_HEIGHT;
                return state.context;
            }
            var canvas = document.createElement("canvas");
            canvas.width = WEBGL_WIDTH;
            canvas.height = WEBGL_HEIGHT;
            var contextType = "webgl";
            var gl = canvas.getContext("webgl", CONTEXT_OPTIONS);
            if (!gl) {
                contextType = "experimental-webgl";
                gl = canvas.getContext("experimental-webgl", CONTEXT_OPTIONS);
            }
            if (!gl) {
                state.disabled = true;
                state.busy = false;
                return null;
            }
            state.context = { canvas: canvas, contextType: contextType, gl: gl, loseExtension: null };
            try {
                state.context.loseExtension = gl.getExtension("WEBGL_lose_context");
            }
            catch (_error) {
                // Extension discovery failures use the same reuse path as missing support.
            }
            return state.context;
        }
        catch (_error) {
            state.disabled = true;
            state.busy = false;
            return null;
        }
    }
    function disableContext(gl) {
        var state = contextState();
        if (state && state.context && state.context.gl === gl)
            state.disabled = true;
    }
    function releaseContext(context) {
        var state = contextState();
        var gl = context.gl;
        try {
            if (context.loseExtension) {
                try {
                    context.loseExtension.loseContext();
                    if (gl.isContextLost()) {
                        if (state)
                            state.context = null;
                        return;
                    }
                }
                catch (_error) {
                    // A throwing or ineffective extension must not cause fresh allocations.
                }
                context.loseExtension = null;
            }
            if (gl.isContextLost()) {
                if (state)
                    state.disabled = true;
                return;
            }
            gl.useProgram(null);
            gl.bindBuffer(gl.ARRAY_BUFFER, null);
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, null);
            gl.bindFramebuffer(gl.FRAMEBUFFER, null);
            gl.bindRenderbuffer(gl.RENDERBUFFER, null);
            gl.activeTexture(gl.TEXTURE0);
            gl.bindTexture(gl.TEXTURE_2D, null);
            var count = gl.getParameter(gl.MAX_VERTEX_ATTRIBS);
            if (typeof count !== "number" || !isFinite(count) || count < 0 || count > 256 || Math.floor(count) !== count) {
                throw new Error("Invalid WebGL vertex attribute limit");
            }
            for (var index = 0; index < count; index += 1)
                gl.disableVertexAttribArray(index);
        }
        catch (_error) {
            if (state)
                state.disabled = true;
        }
        finally {
            try {
                // Shrink idle storage; this does not destroy a retained context.
                context.canvas.width = 1;
                context.canvas.height = 1;
            }
            catch (_error) {
                if (state)
                    state.disabled = true;
            }
            if (state)
                state.busy = false;
        }
    }
    function deleteResource(gl, kind, resource) {
        if (!resource)
            return;
        try {
            switch (kind) {
                case "buffer":
                    gl.deleteBuffer(resource);
                    break;
                case "texture":
                    gl.deleteTexture(resource);
                    break;
                case "program":
                    gl.deleteProgram(resource);
                    break;
                case "shader":
                    gl.deleteShader(resource);
                    break;
            }
        }
        catch (_error) {
            // Keep attempting other deletions, but do not reuse a dirty context.
            disableContext(gl);
        }
    }
    function readVersion(gl) {
        try {
            return normalizeVersion(safeString(gl.getParameter(gl.VERSION)));
        }
        catch (_error) {
            return null;
        }
    }
    function prepareContext(gl) {
        gl.viewport(0, 0, WEBGL_WIDTH, WEBGL_HEIGHT);
        gl.disable(gl.DITHER);
        gl.disable(gl.BLEND);
        gl.disable(gl.DEPTH_TEST);
        gl.disable(gl.CULL_FACE);
        gl.disable(gl.SCISSOR_TEST);
        gl.colorMask(true, true, true, true);
    }
    function clearErrors(gl) {
        var error = gl.getError();
        var attempts = 0;
        while (error !== gl.NO_ERROR && attempts < 8) {
            error = gl.getError();
            attempts += 1;
        }
    }
    function compileProgram(gl, vertexSource, fragmentSource) {
        var vertexShader = null;
        var fragmentShader = null;
        var program = null;
        try {
            vertexShader = gl.createShader(gl.VERTEX_SHADER);
            fragmentShader = gl.createShader(gl.FRAGMENT_SHADER);
            if (!vertexShader || !fragmentShader)
                return null;
            gl.shaderSource(vertexShader, vertexSource);
            gl.compileShader(vertexShader);
            if (!gl.getShaderParameter(vertexShader, gl.COMPILE_STATUS))
                return null;
            gl.shaderSource(fragmentShader, fragmentSource);
            gl.compileShader(fragmentShader);
            if (!gl.getShaderParameter(fragmentShader, gl.COMPILE_STATUS))
                return null;
            program = gl.createProgram();
            if (!program)
                return null;
            gl.attachShader(program, vertexShader);
            gl.attachShader(program, fragmentShader);
            gl.linkProgram(program);
            if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
                deleteResource(gl, "program", program);
                return null;
            }
            return program;
        }
        catch (_error) {
            deleteResource(gl, "program", program);
            return null;
        }
        finally {
            deleteResource(gl, "shader", vertexShader);
            deleteResource(gl, "shader", fragmentShader);
        }
    }
    function uploadBuffer(gl, values) {
        var buffer = null;
        try {
            buffer = gl.createBuffer();
            if (!buffer)
                return null;
            gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
            gl.bufferData(gl.ARRAY_BUFFER, values, gl.STATIC_DRAW);
            return buffer;
        }
        catch (_error) {
            deleteResource(gl, "buffer", buffer);
            return null;
        }
    }
    function readPixels(gl) {
        try {
            var pixels = new Uint8Array(WEBGL_WIDTH * WEBGL_HEIGHT * 4);
            gl.readPixels(0, 0, WEBGL_WIDTH, WEBGL_HEIGHT, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
            if (gl.getError() !== gl.NO_ERROR)
                return null;
            return pixels;
        }
        catch (_error) {
            return null;
        }
    }
    function drawSolid(gl, program, positions, mode) {
        var buffer = null;
        try {
            buffer = uploadBuffer(gl, positions);
            if (!buffer)
                return null;
            var location = gl.getAttribLocation(program, "aPosition");
            if (location < 0)
                return null;
            gl.useProgram(program);
            gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
            gl.enableVertexAttribArray(location);
            gl.vertexAttribPointer(location, 2, gl.FLOAT, false, 0, 0);
            gl.drawArrays(mode, 0, positions.length / 2);
            return readPixels(gl);
        }
        catch (_error) {
            return null;
        }
        finally {
            deleteResource(gl, "buffer", buffer);
        }
    }
    function drawTexture(gl, program) {
        var positionBuffer = null;
        var texCoordBuffer = null;
        var texture = null;
        try {
            positionBuffer = uploadBuffer(gl, QUAD_POSITIONS);
            texCoordBuffer = uploadBuffer(gl, QUAD_TEX_COORDS);
            if (!positionBuffer || !texCoordBuffer)
                return null;
            texture = gl.createTexture();
            if (!texture)
                return null;
            gl.activeTexture(gl.TEXTURE0);
            gl.bindTexture(gl.TEXTURE_2D, texture);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 4, 4, 0, gl.RGBA, gl.UNSIGNED_BYTE, CHECKER_TEXTURE);
            var positionLocation = gl.getAttribLocation(program, "aPosition");
            var texCoordLocation = gl.getAttribLocation(program, "aTexCoord");
            var samplerLocation = gl.getUniformLocation(program, "uTexture");
            if (positionLocation < 0 || texCoordLocation < 0 || samplerLocation === null)
                return null;
            gl.useProgram(program);
            gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
            gl.enableVertexAttribArray(positionLocation);
            gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);
            gl.bindBuffer(gl.ARRAY_BUFFER, texCoordBuffer);
            gl.enableVertexAttribArray(texCoordLocation);
            gl.vertexAttribPointer(texCoordLocation, 2, gl.FLOAT, false, 0, 0);
            gl.uniform1i(samplerLocation, 0);
            gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
            return readPixels(gl);
        }
        catch (_error) {
            return null;
        }
        finally {
            deleteResource(gl, "buffer", positionBuffer);
            deleteResource(gl, "buffer", texCoordBuffer);
            deleteResource(gl, "texture", texture);
        }
    }
    function runRedSample(gl) {
        var program = null;
        try {
            prepareContext(gl);
            clearErrors(gl);
            gl.clearColor(0, 0, 0, 1);
            gl.clear(gl.COLOR_BUFFER_BIT);
            program = compileProgram(gl, RED_VERTEX_SHADER, SOLID_RED_FRAGMENT_SHADER);
            if (!program)
                return null;
            return drawSolid(gl, program, RED_RECT_POSITIONS, gl.TRIANGLE_STRIP);
        }
        catch (_error) {
            return null;
        }
        finally {
            deleteResource(gl, "program", program);
        }
    }
    function runRenderSample(gl) {
        var geometryProgram = null;
        var textureProgram = null;
        try {
            prepareContext(gl);
            clearErrors(gl);
            gl.clearColor(0, 0, 1, 1);
            gl.clear(gl.COLOR_BUFFER_BIT);
            geometryProgram = compileProgram(gl, RED_VERTEX_SHADER, SOLID_RED_FRAGMENT_SHADER);
            if (!geometryProgram)
                return null;
            var geometryPixels = drawSolid(gl, geometryProgram, TRIANGLE_POSITIONS, gl.TRIANGLES);
            if (!geometryPixels)
                return null;
            gl.clearColor(0, 0, 0, 1);
            gl.clear(gl.COLOR_BUFFER_BIT);
            textureProgram = compileProgram(gl, TEXTURE_VERTEX_SHADER, TEXTURE_FRAGMENT_SHADER);
            if (!textureProgram)
                return null;
            var texturePixels = drawTexture(gl, textureProgram);
            if (!texturePixels)
                return null;
            var combined = new Uint8Array(geometryPixels.length + texturePixels.length);
            combined.set(geometryPixels, 0);
            combined.set(texturePixels, geometryPixels.length);
            return combined;
        }
        catch (_error) {
            return null;
        }
        finally {
            deleteResource(gl, "program", geometryProgram);
            deleteResource(gl, "program", textureProgram);
        }
    }
    function rightRotate(value, bits) {
        return (value >>> bits) | (value << (32 - bits));
    }
    function choose(x, y, z) {
        return (x & y) ^ (~x & z);
    }
    function majority(x, y, z) {
        return (x & y) ^ (x & z) ^ (y & z);
    }
    function smallSigma0(value) {
        return rightRotate(value, 7) ^ rightRotate(value, 18) ^ (value >>> 3);
    }
    function smallSigma1(value) {
        return rightRotate(value, 17) ^ rightRotate(value, 19) ^ (value >>> 10);
    }
    function bigSigma0(value) {
        return rightRotate(value, 2) ^ rightRotate(value, 13) ^ rightRotate(value, 22);
    }
    function bigSigma1(value) {
        return rightRotate(value, 6) ^ rightRotate(value, 11) ^ rightRotate(value, 25);
    }
    function writeWord(bytes, offset, value) {
        bytes[offset] = (value >>> 24) & 0xff;
        bytes[offset + 1] = (value >>> 16) & 0xff;
        bytes[offset + 2] = (value >>> 8) & 0xff;
        bytes[offset + 3] = value & 0xff;
    }
    function wordToHex(value) {
        return ("00000000" + (value >>> 0).toString(16)).slice(-8);
    }
    /** Returns the first 128 bits of SHA-256 as lowercase hexadecimal. */
    function sha256Bytes(value) {
        var sha256K = [
            0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
            0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
            0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
            0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
            0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
            0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
            0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
            0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
            0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
            0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
            0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
            0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
            0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
            0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
            0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
            0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
        ];
        var bitLength = value.length * 8;
        var paddedLength = Math.ceil((value.length + 9) / 64) * 64;
        var padded = new Uint8Array(paddedLength);
        var i;
        var offset;
        var round;
        var word;
        var schedule;
        var a;
        var b;
        var c;
        var d;
        var e;
        var f;
        var g;
        var h;
        var temp1;
        var temp2;
        var h0 = 0x6a09e667;
        var h1 = 0xbb67ae85;
        var h2 = 0x3c6ef372;
        var h3 = 0xa54ff53a;
        var h4 = 0x510e527f;
        var h5 = 0x9b05688c;
        var h6 = 0x1f83d9ab;
        var h7 = 0x5be0cd19;
        var highLength = Math.floor(bitLength / 0x100000000);
        var lowLength = bitLength >>> 0;
        for (i = 0; i < value.length; i += 1)
            padded[i] = value[i];
        padded[value.length] = 0x80;
        writeWord(padded, paddedLength - 8, highLength);
        writeWord(padded, paddedLength - 4, lowLength);
        for (offset = 0; offset < paddedLength; offset += 64) {
            schedule = [];
            for (i = 0; i < 16; i += 1) {
                word = (padded[offset + i * 4] << 24)
                    | (padded[offset + i * 4 + 1] << 16)
                    | (padded[offset + i * 4 + 2] << 8)
                    | padded[offset + i * 4 + 3];
                schedule[i] = word >>> 0;
            }
            for (i = 16; i < 64; i += 1) {
                schedule[i] = (smallSigma1(schedule[i - 2]) + schedule[i - 7]
                    + smallSigma0(schedule[i - 15]) + schedule[i - 16]) >>> 0;
            }
            a = h0;
            b = h1;
            c = h2;
            d = h3;
            e = h4;
            f = h5;
            g = h6;
            h = h7;
            for (round = 0; round < 64; round += 1) {
                temp1 = (h + bigSigma1(e) + choose(e, f, g) + sha256K[round] + schedule[round]) >>> 0;
                temp2 = (bigSigma0(a) + majority(a, b, c)) >>> 0;
                h = g;
                g = f;
                f = e;
                e = (d + temp1) >>> 0;
                d = c;
                c = b;
                b = a;
                a = (temp1 + temp2) >>> 0;
            }
            h0 = (h0 + a) >>> 0;
            h1 = (h1 + b) >>> 0;
            h2 = (h2 + c) >>> 0;
            h3 = (h3 + d) >>> 0;
            h4 = (h4 + e) >>> 0;
            h5 = (h5 + f) >>> 0;
            h6 = (h6 + g) >>> 0;
            h7 = (h7 + h) >>> 0;
        }
        return wordToHex(h0) + wordToHex(h1) + wordToHex(h2) + wordToHex(h3);
    }
    function sampleFromContext(runner) {
        var context = acquireContext();
        if (!context)
            return emptySample();
        var gl = context.gl;
        var version = readVersion(gl);
        try {
            var pixels = runner(gl);
            return { supported: true, version: version, hash: pixels ? sha256Bytes(pixels) : null };
        }
        catch (_error) {
            return { supported: true, version: version, hash: null };
        }
        finally {
            releaseContext(context);
        }
    }
    function collectWebGLRedSample() {
        return sampleFromContext(runRedSample);
    }
    function collectWebGLRenderSample() {
        return sampleFromContext(runRenderSample);
    }
    function readNumberParameter(gl, parameter) {
        try {
            var value = gl.getParameter(parameter);
            return typeof value === "number" && isFinite(value) ? value : null;
        }
        catch (_error) {
            return null;
        }
    }
    function readStringParameter(gl, parameter) {
        try {
            return safeString(gl.getParameter(parameter));
        }
        catch (_error) {
            return null;
        }
    }
    function readBoundedStringParameter(gl, parameter) {
        var value = readStringParameter(gl, parameter);
        return value && value.length > MAX_RENDERER_INFO_LENGTH
            ? value.slice(0, MAX_RENDERER_INFO_LENGTH)
            : value;
    }
    function readContextAttributes(gl) {
        try {
            var attributes = gl.getContextAttributes();
            if (!attributes)
                return null;
            return {
                alpha: attributes.alpha === undefined ? null : attributes.alpha,
                antialias: attributes.antialias === undefined ? null : attributes.antialias,
                depth: attributes.depth === undefined ? null : attributes.depth,
                stencil: attributes.stencil === undefined ? null : attributes.stencil,
                preserveDrawingBuffer: attributes.preserveDrawingBuffer === undefined ? null : attributes.preserveDrawingBuffer,
            };
        }
        catch (_error) {
            return null;
        }
    }
    function readDebugRendererInfo(gl) {
        try {
            var extension = gl.getExtension("WEBGL_debug_renderer_info");
            if (!extension)
                return { unmaskedVendor: null, unmaskedRenderer: null };
            return {
                unmaskedVendor: readBoundedStringParameter(gl, extension.UNMASKED_VENDOR_WEBGL),
                unmaskedRenderer: readBoundedStringParameter(gl, extension.UNMASKED_RENDERER_WEBGL),
            };
        }
        catch (_error) {
            return { unmaskedVendor: null, unmaskedRenderer: null };
        }
    }
    /**
     * Reads the optional underlying graphics driver strings without running a
     * render pass. Browsers may omit WEBGL_debug_renderer_info for privacy, so a
     * missing extension or failed read is represented by null values.
     */
    function collectWebGLRendererInfo() {
        var context = acquireContext();
        if (!context)
            return { unmaskedVendor: null, unmaskedRenderer: null };
        try {
            return readDebugRendererInfo(context.gl);
        }
        finally {
            releaseContext(context);
        }
    }
    function readErrorCodes(gl, stage) {
        var errors = [];
        var code = gl.getError();
        var attempts = 0;
        while (code !== gl.NO_ERROR && attempts < 8) {
            errors.push({ stage: stage, code: code });
            code = gl.getError();
            attempts += 1;
        }
        return errors;
    }
    function emptyDebugSample() {
        return {
            supported: false,
            version: null,
            hash: null,
            contextType: null,
            canvas: { width: WEBGL_WIDTH, height: WEBGL_HEIGHT },
            contextAttributes: null,
            implementation: {
                vendor: null,
                renderer: null,
                unmaskedVendor: null,
                unmaskedRenderer: null,
                shadingLanguageVersion: null,
                supportedExtensions: [],
                maxTextureSize: null,
                maxViewportWidth: null,
                maxViewportHeight: null,
            },
            render: {
                viewport: [0, 0, WEBGL_WIDTH, WEBGL_HEIGHT],
                disabledStates: ["DITHER", "BLEND", "DEPTH_TEST", "CULL_FACE", "SCISSOR_TEST"],
                hashAlgorithm: "SHA-256 truncated to first 128 bits",
                pixelFormat: "RGBA / UNSIGNED_BYTE",
                geometry: { primitive: "TRIANGLES", vertexCount: 3, pixelBytes: 0, hash: null },
                texture: { primitive: "TRIANGLE_STRIP", vertexCount: 4, textureSize: "4x4 RGBA checkerboard", pixelBytes: 0, hash: null },
                combinedPixelBytes: 0,
            },
            errors: [],
        };
    }
    /**
     * Runs the same render recipe as collectWebGLRenderSample, while retaining
     * enough metadata to explain hash differences. This is intended for local
     * diagnostics and should not be added to the event payload.
     */
    function collectWebGLRenderDebugSampleUnsafe() {
        var context = acquireContext();
        if (!context)
            return emptyDebugSample();
        try {
            return renderDebugSample(context);
        }
        finally {
            releaseContext(context);
        }
    }
    function renderDebugSample(context) {
        var gl = context.gl;
        var debug = emptyDebugSample();
        debug.supported = true;
        debug.contextType = context.contextType;
        debug.version = readVersion(gl);
        debug.contextAttributes = readContextAttributes(gl);
        var rendererInfo = readDebugRendererInfo(gl);
        var extensions = [];
        try {
            extensions = gl.getSupportedExtensions() || [];
        }
        catch (_error) {
            extensions = [];
        }
        debug.implementation = {
            vendor: readStringParameter(gl, gl.VENDOR),
            renderer: readStringParameter(gl, gl.RENDERER),
            unmaskedVendor: rendererInfo.unmaskedVendor,
            unmaskedRenderer: rendererInfo.unmaskedRenderer,
            shadingLanguageVersion: readStringParameter(gl, gl.SHADING_LANGUAGE_VERSION),
            supportedExtensions: extensions,
            maxTextureSize: readNumberParameter(gl, gl.MAX_TEXTURE_SIZE),
            maxViewportWidth: null,
            maxViewportHeight: null,
        };
        try {
            var viewportDimensions = gl.getParameter(gl.MAX_VIEWPORT_DIMS);
            if (viewportDimensions && viewportDimensions.length >= 2) {
                debug.implementation.maxViewportWidth = viewportDimensions[0];
                debug.implementation.maxViewportHeight = viewportDimensions[1];
            }
        }
        catch (_error) {
            // Keep the optional limit fields null when the implementation hides them.
        }
        var geometryProgram = null;
        var textureProgram = null;
        var geometryPixels = null;
        var texturePixels = null;
        try {
            prepareContext(gl);
            clearErrors(gl);
            debug.errors = debug.errors.concat(readErrorCodes(gl, "prepare"));
            gl.clearColor(0, 0, 1, 1);
            gl.clear(gl.COLOR_BUFFER_BIT);
            geometryProgram = compileProgram(gl, RED_VERTEX_SHADER, SOLID_RED_FRAGMENT_SHADER);
            geometryPixels = geometryProgram
                ? drawSolid(gl, geometryProgram, TRIANGLE_POSITIONS, gl.TRIANGLES)
                : null;
            debug.errors = debug.errors.concat(readErrorCodes(gl, "geometry"));
            gl.clearColor(0, 0, 0, 1);
            gl.clear(gl.COLOR_BUFFER_BIT);
            textureProgram = compileProgram(gl, TEXTURE_VERTEX_SHADER, TEXTURE_FRAGMENT_SHADER);
            texturePixels = textureProgram ? drawTexture(gl, textureProgram) : null;
            debug.errors = debug.errors.concat(readErrorCodes(gl, "texture"));
        }
        catch (_error) {
            debug.errors = debug.errors.concat(readErrorCodes(gl, "render"));
        }
        finally {
            deleteResource(gl, "program", geometryProgram);
            deleteResource(gl, "program", textureProgram);
        }
        var geometryHash = geometryPixels ? sha256Bytes(geometryPixels) : null;
        var textureHash = texturePixels ? sha256Bytes(texturePixels) : null;
        var combinedBytes = geometryPixels && texturePixels
            ? geometryPixels.length + texturePixels.length
            : 0;
        var combined = geometryPixels && texturePixels ? new Uint8Array(combinedBytes) : null;
        if (combined && geometryPixels && texturePixels) {
            combined.set(geometryPixels, 0);
            combined.set(texturePixels, geometryPixels.length);
        }
        debug.hash = combined ? sha256Bytes(combined) : null;
        debug.render.geometry.pixelBytes = geometryPixels ? geometryPixels.length : 0;
        debug.render.geometry.hash = geometryHash;
        debug.render.texture.pixelBytes = texturePixels ? texturePixels.length : 0;
        debug.render.texture.hash = textureHash;
        debug.render.combinedPixelBytes = combinedBytes;
        return debug;
    }
    /**
     * Debug collection is optional and must be completely isolated from the
     * production collection lifecycle. Browser/WebView WebGL implementations can
     * throw from any API, including cleanup methods, so keep a final no-throw
     * boundary around the detailed probe.
     */
    function collectWebGLRenderDebugSample() {
        try {
            return collectWebGLRenderDebugSampleUnsafe();
        }
        catch (_error) {
            return emptyDebugSample();
        }
    }

    /**
     * Dynamic WebGL sampling is deliberately capped in source code. Do not make
     * this configurable from the page or from a remote artifact: a dynamic
     * collector may perform at most three red probes and three render probes.
     */
    var MAX_WEBGL_SAMPLES = 3;
    function errorText$1(error, fallback) {
      var message = "";
      try {
        if (error instanceof Error && error.message) {
          message = error.message;
        } else if (typeof error === "string") {
          message = error;
        } else if (error && typeof error.message === "string") {
          message = String(error.message);
        } else if (error !== null && error !== undefined) {
          message = String(error);
        }
      } catch (_error) {
        message = "";
      }
      message = message.replace(/\s+/g, " ").trim();
      return (message || fallback).slice(0, 256);
    }
    function addError$1(errors, field, value, fallback) {
      if (fallback === void 0) {
        fallback = "WebGL field collection failed";
      }
      try {
        var normalizedField = String(field).slice(0, 128);
        var normalizedText = errorText$1(value, fallback);
        for (var index = 0; index < errors.length; index += 1) {
          if (errors[index].field === normalizedField && errors[index].text === normalizedText) return;
        }
        if (errors.length < 16) {
          errors.push({
            field: normalizedField,
            text: normalizedText
          });
        }
      } catch (_error) {
        // Error diagnostics are best effort and must never affect collection.
      }
    }
    function getDebugStore() {
      try {
        var root = window;
        return root.__DYNAMIC_COLLECT_DEBUG__ || null;
      } catch (_error) {
        return null;
      }
    }
    function collectWebGLProbe() {
      var redHashes = [];
      var renderHashes = [];
      var errors = [];
      var renderDebug = [];
      var debugStore = getDebugStore();
      var rendererInfo = {
        unmaskedVendor: null,
        unmaskedRenderer: null
      };
      try {
        rendererInfo = collectWebGLRendererInfo();
      } catch (error) {
        addError$1(errors, "unmaskedVendor", error, "WebGL renderer information unavailable");
        addError$1(errors, "unmaskedRenderer", error, "WebGL renderer information unavailable");
      }
      for (var index = 0; index < MAX_WEBGL_SAMPLES; index += 1) {
        try {
          var redSample = collectWebGLRedSample();
          var redHash = redSample.hash;
          if (redHash) redHashes.push(redHash);else if (!redSample.supported) addError$1(errors, "webglRedHashData", "WebGL context unavailable", "WebGL context unavailable");else addError$1(errors, "webglRedHashData", "WebGL red render pixels unavailable", "WebGL red render pixels unavailable");
        } catch (error) {
          // Keep the successful samples from other rounds.
          addError$1(errors, "webglRedHashData", error, "WebGL red sample failed");
        }
        try {
          if (debugStore) {
            var debugSample = collectWebGLRenderDebugSample();
            renderDebug.push(debugSample);
            if (debugSample.hash) renderHashes.push(debugSample.hash);else if (!debugSample.supported) addError$1(errors, "webglHashData", "WebGL context unavailable", "WebGL context unavailable");else addError$1(errors, "webglHashData", "WebGL render pixels unavailable", "WebGL render pixels unavailable");
          } else {
            var renderSample = collectWebGLRenderSample();
            var renderHash = renderSample.hash;
            if (renderHash) renderHashes.push(renderHash);else if (!renderSample.supported) addError$1(errors, "webglHashData", "WebGL context unavailable", "WebGL context unavailable");else addError$1(errors, "webglHashData", "WebGL render pixels unavailable", "WebGL render pixels unavailable");
          }
        } catch (error) {
          // Keep the successful samples from other rounds.
          addError$1(errors, "webglHashData", error, "WebGL render sample failed");
        }
      }
      if (debugStore) {
        try {
          if (!debugStore.webgl) debugStore.webgl = {};
          debugStore.webgl.dynamic = renderDebug;
        } catch (_error) {
          // Debug output is optional and must not affect production collection.
        }
      }
      return {
        redHashes: redHashes,
        renderHashes: renderHashes,
        unmaskedVendor: rendererInfo.unmaskedVendor,
        unmaskedRenderer: rendererInfo.unmaskedRenderer,
        errors: errors,
        renderDebug: debugStore ? renderDebug : undefined
      };
    }

    /******************************************************************************
    Copyright (c) Microsoft Corporation.

    Permission to use, copy, modify, and/or distribute this software for any
    purpose with or without fee is hereby granted.

    THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
    REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
    AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
    INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
    LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
    OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
    PERFORMANCE OF THIS SOFTWARE.
    ***************************************************************************** */
    /* global Reflect, Promise, SuppressedError, Symbol, Iterator */


    var __assign = function() {
        __assign = Object.assign || function __assign(t) {
            for (var s, i = 1, n = arguments.length; i < n; i++) {
                s = arguments[i];
                for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p)) t[p] = s[p];
            }
            return t;
        };
        return __assign.apply(this, arguments);
    };

    typeof SuppressedError === "function" ? SuppressedError : function (error, suppressed, message) {
        var e = new Error(message);
        return e.name = "SuppressedError", e.error = error, e.suppressed = suppressed, e;
    };

    var DYNAMIC_COLLECTOR_ID = "browser-signals";
    var DYNAMIC_COLLECTOR_VERSION = "1.0.0";
    var DYNAMIC_COLLECTOR_SCHEMA_VERSION = "1.1";
    var BASE_TAGS = {
      sentryProjectSlug: "dynamic-collect",
      collectorId: DYNAMIC_COLLECTOR_ID,
      collectorVersion: DYNAMIC_COLLECTOR_VERSION,
      schemaVersion: DYNAMIC_COLLECTOR_SCHEMA_VERSION
    };
    function getErrorText(value, fallback) {
      try {
        var text = value instanceof Error ? value.message : typeof value === "string" ? value : value && typeof value.message === "string" ? String(value.message) : String(value || "");
        return (text.replace(/\s+/g, " ").trim() || fallback).slice(0, 256);
      } catch (_error) {
        return fallback;
      }
    }
    function getTags(tags) {
      return __assign(__assign({}, BASE_TAGS), tags || {});
    }
    function getSentry() {
      try {
        if (typeof window === "undefined") return undefined;
        return window.Sentry;
      } catch (_error) {
        return undefined;
      }
    }
    function reportSentryMessage(message, tags) {
      var _a, _b;
      try {
        (_b = (_a = getSentry()) === null || _a === void 0 ? void 0 : _a.captureMessage) === null || _b === void 0 ? void 0 : _b.call(_a, message, {
          tags: getTags(tags)
        });
      } catch (_error) {
        // Sentry is optional and must never affect collection or the host page.
      }
    }
    function reportSentryError(error, tags) {
      var _a, _b;
      try {
        (_b = (_a = getSentry()) === null || _a === void 0 ? void 0 : _a.captureException) === null || _b === void 0 ? void 0 : _b.call(_a, error, {
          tags: getTags(tags)
        });
      } catch (_error) {
        // Sentry is optional and must never affect collection or the host page.
      }
    }
    function contextTags(context) {
      var tags = {};
      if (context === null || context === void 0 ? void 0 : context.env) tags.env = context.env;
      if (context === null || context === void 0 ? void 0 : context.locale) tags.locale = context.locale;
      if (context === null || context === void 0 ? void 0 : context.scene) tags.scene = context.scene;
      return tags;
    }
    function reportDynamicCollectionErrors(records, context) {
      try {
        if (!records || records.length === 0) return;
        var maxReports = Math.min(records.length, 16);
        for (var index = 0; index < maxReports; index += 1) {
          var record = records[index];
          var detail = getErrorText(record.text, "Dynamic field collection failed");
          reportSentryMessage("dynamic " + DYNAMIC_COLLECTOR_ID + " " + record.field + " error: " + detail, __assign(__assign({}, contextTags(context)), {
            errorField: record.field
          }));
        }
      } catch (_error) {
        // Error reporting is best effort and must never affect collection.
      }
    }
    function reportDynamicCollectorException(value, context) {
      try {
        var detail = getErrorText(value, "Dynamic collector failed");
        var error = new Error("dynamic " + DYNAMIC_COLLECTOR_ID + " collector error: " + detail);
        reportSentryError(error, __assign(__assign({}, contextTags(context)), {
          errorField: "collector"
        }));
      } catch (_error) {
        // Error reporting is best effort and must never affect collection.
      }
    }

    var MAX_COLLECTION_ERRORS = 16;
    var MAX_ERROR_FIELD_LENGTH = 128;
    var MAX_ERROR_TEXT_LENGTH = 256;
    function createErrorState() {
      return {
        fields: [],
        texts: [],
        records: []
      };
    }
    function errorText(error, fallback) {
      var message = "";
      try {
        if (error instanceof Error && error.message) {
          message = error.message;
        } else if (typeof error === "string") {
          message = error;
        } else if (error && typeof error.message === "string") {
          message = String(error.message);
        } else if (error !== null && error !== undefined) {
          message = String(error);
        }
      } catch (_error) {
        message = "";
      }
      message = message.replace(/\s+/g, " ").trim();
      return (message || fallback).slice(0, MAX_ERROR_TEXT_LENGTH);
    }
    function addError(state, field, error, fallback) {
      try {
        var normalizedField = String(field).slice(0, MAX_ERROR_FIELD_LENGTH);
        var normalizedText = errorText(error, fallback);
        for (var index = 0; index < state.fields.length; index += 1) {
          if (state.fields[index] === normalizedField && state.texts[index] === normalizedText) return;
        }
        if (state.fields.length >= MAX_COLLECTION_ERRORS) return;
        state.fields.push(normalizedField);
        state.texts.push(normalizedText);
        state.records.push({
          field: normalizedField,
          text: normalizedText
        });
      } catch (_error) {
        // Error diagnostics are best effort and must never affect collection.
      }
    }
    function readField(state, field, reader, fallback, fallbackText) {
      try {
        return reader();
      } catch (error) {
        addError(state, field, error, fallbackText);
        return fallback;
      }
    }
    function storageAvailable(name) {
      var storage = window[name];
      if (!storage) throw new Error(name + " API unavailable");
      var key = "__dynamic_collect_probe__";
      storage.setItem(key, "1");
      storage.removeItem(key);
      return true;
    }
    function emptyPayload(state, context) {
      reportDynamicCollectionErrors(state.records, context);
      return {
        base: {},
        dynamic: {
          webglHashData: [],
          webglRedHashData: [],
          webglRenderHashAfter: null,
          unmaskedVendor: null,
          unmaskedRenderer: null,
          error_field: state.fields,
          error_text: state.texts
        }
      };
    }
    function collectBrowserSignals(context) {
      var errors = createErrorState();
      try {
        if (typeof window === "undefined") {
          addError(errors, "browser", "window is unavailable", "Browser global unavailable");
          return emptyPayload(errors, context);
        }
        // The dynamic artifact owns repeated WebGL sampling. collectWebGLProbe has
        // a source-level MAX_WEBGL_SAMPLES=3 cap; the SDK itself samples only once.
        var webgl = readField(errors, "webgl", collectWebGLProbe, {
          redHashes: [],
          renderHashes: [],
          unmaskedVendor: null,
          unmaskedRenderer: null,
          errors: []
        }, "WebGL probe failed");
        if (webgl && Array.isArray(webgl.errors)) {
          webgl.errors.forEach(function addWebGLError(item) {
            if (item && typeof item.field === "string" && typeof item.text === "string") {
              addError(errors, item.field, item.text, "WebGL field collection failed");
            }
          });
        }
        var href = readField(errors, "href", function readHref() {
          return String(window.location && window.location.href || "");
        }, "", "Page href unavailable");
        var devicePixelRatio = readField(errors, "devicePixelRatio", function readDevicePixelRatio() {
          return window.devicePixelRatio || 1;
        }, 1, "devicePixelRatio unavailable");
        var colorDepth = readField(errors, "colorDepth", function readColorDepth() {
          if (!window.screen) throw new Error("Screen API unavailable");
          return window.screen.colorDepth;
        }, null, "colorDepth unavailable");
        var hardwareConcurrency = readField(errors, "hardwareConcurrency", function readHardwareConcurrency() {
          if (!window.navigator) throw new Error("Navigator API unavailable");
          return window.navigator.hardwareConcurrency || null;
        }, null, "hardwareConcurrency unavailable");
        var maxTouchPoints = readField(errors, "maxTouchPoints", function readMaxTouchPoints() {
          if (!window.navigator) throw new Error("Navigator API unavailable");
          return window.navigator.maxTouchPoints || 0;
        }, 0, "maxTouchPoints unavailable");
        var localStorageAvailable = readField(errors, "localStorageAvailable", function readLocalStorage() {
          return storageAvailable("localStorage");
        }, false, "localStorage unavailable");
        var sessionStorageAvailable = readField(errors, "sessionStorageAvailable", function readSessionStorage() {
          return storageAvailable("sessionStorage");
        }, false, "sessionStorage unavailable");
        var indexedDBAvailable = readField(errors, "indexedDBAvailable", function readIndexedDB() {
          return Boolean(window.indexedDB);
        }, false, "indexedDB unavailable");
        reportDynamicCollectionErrors(errors.records, context);
        return {
          base: {
            href: href
          },
          dynamic: {
            devicePixelRatio: devicePixelRatio,
            colorDepth: colorDepth,
            hardwareConcurrency: hardwareConcurrency,
            maxTouchPoints: maxTouchPoints,
            localStorageAvailable: localStorageAvailable,
            sessionStorageAvailable: sessionStorageAvailable,
            indexedDBAvailable: indexedDBAvailable,
            webglHashData: webgl.renderHashes,
            webglRedHashData: webgl.redHashes,
            webglRenderHashAfter: webgl.renderHashes.length > 0 ? webgl.renderHashes[0] : null,
            unmaskedVendor: webgl.unmaskedVendor,
            unmaskedRenderer: webgl.unmaskedRenderer,
            error_field: errors.fields,
            error_text: errors.texts
          }
        };
      } catch (error) {
        addError(errors, "collector", error, "Browser signal collection failed");
        return emptyPayload(errors, context);
      }
    }

    registerCollector({
      id: DYNAMIC_COLLECTOR_ID,
      version: DYNAMIC_COLLECTOR_VERSION,
      schemaVersion: DYNAMIC_COLLECTOR_SCHEMA_VERSION,
      collect: function collect(context, callback) {
        var payload = {
          base: {},
          dynamic: {}
        };
        try {
          payload = collectBrowserSignals(context);
        } catch (error) {
          // Keep the empty fallback and still complete the callback once.
          reportDynamicCollectorException(error, context);
        }
        try {
          callback(null, payload);
        } catch (_callbackError) {
          // The artifact is a page-level script. Consumer callback failures must
          // not escape as an uncaught exception.
        }
      }
    });

})();
//# sourceMappingURL=browser-signals.iife.js.map
