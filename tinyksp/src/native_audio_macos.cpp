#include "native_audio_macos.h"

#include <AudioToolbox/AudioToolbox.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <new>
#include <thread>
#include <vector>

namespace tinyksp {
namespace {
constexpr uint32_t SAMPLE_RATE = 44100;
constexpr uint32_t CHANNELS = 2;
constexpr uint32_t BYTES_PER_FRAME = CHANNELS * sizeof(int16_t);
constexpr uint32_t QUEUE_BUFFER_FRAMES = 1024;
constexpr uint32_t QUEUE_BUFFER_COUNT = 3;
constexpr uint32_t RING_BUFFER_FRAMES = SAMPLE_RATE / 2;

std::string audioError(const char* operation, OSStatus status) {
    return std::string(operation) + " failed (OSStatus " +
           std::to_string(static_cast<int32_t>(status)) + ")";
}
} // namespace

struct MacAudioOutput::Impl {
    AudioQueueRef queue = nullptr;
    AudioQueueBufferRef buffers[QUEUE_BUFFER_COUNT]{};
    std::vector<int16_t> ring;
    std::atomic<uint64_t> read_position{0};
    std::atomic<uint64_t> write_position{0};
    std::atomic<bool> running{false};

    static void audioQueueCallback(void* user_data, AudioQueueRef queue,
                                   AudioQueueBufferRef buffer);

    void fillBuffer(AudioQueueBufferRef buffer) {
        const uint32_t capacity_frames =
            static_cast<uint32_t>(buffer->mAudioDataBytesCapacity / BYTES_PER_FRAME);
        const uint64_t read = read_position.load(std::memory_order_relaxed);
        const uint64_t write = write_position.load(std::memory_order_acquire);
        const uint64_t available = write - read;
        const uint32_t copied = static_cast<uint32_t>(
            std::min<uint64_t>(available, capacity_frames));
        auto* destination = static_cast<int16_t*>(buffer->mAudioData);

        for (uint32_t frame = 0; frame < copied; ++frame) {
            const uint64_t source_frame = (read + frame) % RING_BUFFER_FRAMES;
            destination[frame * CHANNELS] = ring[source_frame * CHANNELS];
            destination[frame * CHANNELS + 1] = ring[source_frame * CHANNELS + 1];
        }
        if (copied < capacity_frames) {
            std::memset(destination + copied * CHANNELS, 0,
                        static_cast<size_t>(capacity_frames - copied) * BYTES_PER_FRAME);
        }
        read_position.store(read + copied, std::memory_order_release);
        buffer->mAudioDataByteSize = capacity_frames * BYTES_PER_FRAME;
    }
};

void MacAudioOutput::Impl::audioQueueCallback(void* user_data, AudioQueueRef queue,
                                              AudioQueueBufferRef buffer) {
    auto* impl = static_cast<MacAudioOutput::Impl*>(user_data);
    impl->fillBuffer(buffer);
    if (impl->running.load(std::memory_order_acquire))
        AudioQueueEnqueueBuffer(queue, buffer, 0, nullptr);
}

MacAudioOutput::MacAudioOutput() : impl_(new (std::nothrow) Impl) {}

MacAudioOutput::~MacAudioOutput() {
    stop();
    delete impl_;
}

bool MacAudioOutput::start(std::string& error) {
    if (!impl_) {
        error = "unable to allocate macOS audio output";
        return false;
    }
    stop();

    impl_->ring.assign(RING_BUFFER_FRAMES * CHANNELS, 0);
    impl_->read_position.store(0, std::memory_order_relaxed);
    impl_->write_position.store(0, std::memory_order_relaxed);

    AudioStreamBasicDescription format{};
    format.mSampleRate = SAMPLE_RATE;
    format.mFormatID = kAudioFormatLinearPCM;
    format.mFormatFlags = kAudioFormatFlagIsSignedInteger |
                          kAudioFormatFlagIsPacked;
    format.mFramesPerPacket = 1;
    format.mChannelsPerFrame = CHANNELS;
    format.mBitsPerChannel = 16;
    format.mBytesPerFrame = BYTES_PER_FRAME;
    format.mBytesPerPacket = BYTES_PER_FRAME;

    OSStatus status = AudioQueueNewOutput(
        &format, Impl::audioQueueCallback, impl_, nullptr, nullptr, 0, &impl_->queue);
    if (status != noErr) {
        error = audioError("AudioQueueNewOutput", status);
        impl_->queue = nullptr;
        return false;
    }

    for (uint32_t i = 0; i < QUEUE_BUFFER_COUNT; ++i) {
        status = AudioQueueAllocateBuffer(
            impl_->queue, QUEUE_BUFFER_FRAMES * BYTES_PER_FRAME, &impl_->buffers[i]);
        if (status != noErr) {
            error = audioError("AudioQueueAllocateBuffer", status);
            stop();
            return false;
        }
        std::memset(impl_->buffers[i]->mAudioData, 0,
                    impl_->buffers[i]->mAudioDataBytesCapacity);
        impl_->buffers[i]->mAudioDataByteSize =
            QUEUE_BUFFER_FRAMES * BYTES_PER_FRAME;
    }

    impl_->running.store(true, std::memory_order_release);
    for (AudioQueueBufferRef buffer : impl_->buffers) {
        status = AudioQueueEnqueueBuffer(impl_->queue, buffer, 0, nullptr);
        if (status != noErr) {
            error = audioError("AudioQueueEnqueueBuffer", status);
            stop();
            return false;
        }
    }

    status = AudioQueueStart(impl_->queue, nullptr);
    if (status != noErr) {
        if (status == kAudioQueueErr_InvalidDevice) {
            error = "no usable macOS audio output device is available";
        } else {
            error = audioError("AudioQueueStart", status);
        }
        stop();
        return false;
    }
    return true;
}

bool MacAudioOutput::restart(std::string& error) {
    stop();
    return start(error);
}

bool MacAudioOutput::write(const int16_t* interleaved_stereo, uint32_t frames,
                           std::string& error) {
    if (!impl_ || !impl_->running.load(std::memory_order_acquire)) {
        error = "macOS audio output is not running";
        return false;
    }
    if (!interleaved_stereo && frames) {
        error = "null macOS audio buffer";
        return false;
    }

    uint32_t written = 0;
    while (written < frames) {
        if (!impl_->running.load(std::memory_order_acquire)) {
            error = "macOS audio output stopped";
            return false;
        }
        const uint64_t read = impl_->read_position.load(std::memory_order_acquire);
        const uint64_t write = impl_->write_position.load(std::memory_order_relaxed);
        const uint64_t queued = write - read;
        if (queued >= RING_BUFFER_FRAMES) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            continue;
        }

        const uint32_t available = static_cast<uint32_t>(RING_BUFFER_FRAMES - queued);
        const uint32_t count = std::min(frames - written, available);
        for (uint32_t frame = 0; frame < count; ++frame) {
            const uint64_t destination_frame = (write + frame) % RING_BUFFER_FRAMES;
            impl_->ring[destination_frame * CHANNELS] =
                interleaved_stereo[(written + frame) * CHANNELS];
            impl_->ring[destination_frame * CHANNELS + 1] =
                interleaved_stereo[(written + frame) * CHANNELS + 1];
        }
        impl_->write_position.store(write + count, std::memory_order_release);
        written += count;
    }
    return true;
}

bool MacAudioOutput::drain(std::string& error) {
    if (!impl_ || !impl_->running.load(std::memory_order_acquire)) {
        error = "macOS audio output is not running";
        return false;
    }
    while (impl_->read_position.load(std::memory_order_acquire) !=
           impl_->write_position.load(std::memory_order_acquire)) {
        if (!impl_->running.load(std::memory_order_acquire)) {
            error = "macOS audio output stopped";
            return false;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    // AudioQueue may still own up to three queued buffers after the ring is
    // empty. Let those buffers reach the hardware before the queue is closed.
    std::this_thread::sleep_for(std::chrono::milliseconds(QUEUE_BUFFER_COUNT * 25));
    return true;
}

void MacAudioOutput::stop() {
    if (!impl_) return;
    impl_->running.store(false, std::memory_order_release);
    if (impl_->queue) {
        AudioQueueStop(impl_->queue, true);
        AudioQueueDispose(impl_->queue, true);
        impl_->queue = nullptr;
    }
    for (auto& buffer : impl_->buffers) buffer = nullptr;
    impl_->read_position.store(0, std::memory_order_relaxed);
    impl_->write_position.store(0, std::memory_order_relaxed);
}

} // namespace tinyksp
