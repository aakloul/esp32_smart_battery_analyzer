//>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
// DIY Smart Multipurpose Battery Tester
// by Open Green Energy, INDIA ( www.opengreenenergy.com )
// Beta Version 
// Last Updated on: 25.10.2024
//>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <JC_Button.h>

//>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
// Bluetooth support
//>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <NimBLEEddystoneTLM.h>
#include <sys/time.h>
#include <esp_sleep.h>
#include <mbedtls/md.h>          // mbedTLS is bundled with the ESP32 Arduino core


#define GPIO_DEEP_SLEEP_DURATION 10 // sleep x seconds and then wake up
#define BEACON_POWER             3  // 3dbm

# define ENDIAN_CHANGE_U16(x) ((((x) & 0xFF00) >> 8) + (((x) & 0xFF) << 8))
# define ENDIAN_CHANGE_U32(x) \
     ((((x) & 0xFF000000) >> 24) + (((x) & 0x00FF0000) >> 8)) + ((((x) & 0xFF00) << 8) + (((x) & 0xFF) << 24))

RTC_DATA_ATTR static time_t   last;      // remember last boot in RTC Memory
RTC_DATA_ATTR static uint32_t bootcount; // remember number of boots in RTC Memory
NimBLEAdvertising*            pAdvertising;
struct timeval                nowTimeStruct;

//#define BEACON_UUID \
//    "8ec76ea3-6668-48da-9866-75be8bc86f4d" // UUID 1 128-Bit (may use linux tool uuidgen or random numbers via https://www.uuidgenerator.net/)

unsigned int count = 1; //Number of messages sent
unsigned long lastAdvertisedVoltage = 0;  // Last voltage advertised in BLE beacon
unsigned long lastAdvertisedTimestamp = 0;  // Last voltage advertised in BLE beacon

char *HMAC_KEY = "secretKey";  // <-- replace with your own secret                      

static const uint8_t MAC_TRUNC_LEN = 4;   // bytes of HMAC to keep (4‑8 is typical)
static const uint16_t ADV_INTERVAL_MS = 1000;
static const uint8_t   EDDYSTONE_UUID[] = {0xAA, 0xFE}; // 0xFEAA (Eddystone)

static uint32_t advCount = 0;   // number of advertisements sent

//>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
// DIY Smart Charger
//>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

// Define OLED display dimensions and reset pin
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1

// Create an instance of the SSD1306 display object
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Define GPIO pins for buttons
#define MODE_PIN D3
#define UP_PIN D6
#define DOWN_PIN D9

// Instantiate Button objects
Button Mode_Button(MODE_PIN, 15, false, true);  // GPIO 3 on XIAO ESP32C3 (D3)
Button UP_Button(UP_PIN, 15, false, true);      // GPIO 6 on XIAO ESP32C3 (D6)
Button Down_Button(DOWN_PIN, 15, false, true);  // GPIO 9 on XIAO ESP32C3 (D9)
unsigned long upLastChange = 0;
unsigned long downLastChange = 0;
unsigned long modeLastChange = 0;

// Mode selection variables
int selectedMode = 0;
bool modeSelected = false;
bool inAnalyzeMode = false;  // To track if analyze mode is running

float cutoffVoltage = 3.0;        // Default cutoff voltage, to be selected by user
const float Min_BAT_level = 2.8;  // Minimum threshold voltage for discharge
const float Max_BAT_level = 3.2;  // Maximum threshold voltage for discharge
const float FULL_BAT_level = 4.18;  // Threshold voltage for stopping charge ( Typical Value is 4.2V )
const float DAMAGE_BAT_level = 2.5;  // Define voltage for damged battery
const float NO_BAT_level = 0.3;  // Define voltage for empty slot 

int Current[] = {0, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000};
int PWM[] = {0, 4, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100};
int Array_Size = sizeof(Current) / sizeof(Current[0]);
int Current_Value = 0;
int currentOffset = 25; // Default offset current
int PWM_Value = 0;
int PWM_Index = 0;

unsigned long Capacity = 0;
float Capacity_f = 0;
float Vref_Voltage = 1.227;  // LM385-1.2V reference voltage ( adjust it for calibration )
float Vcc = 3.3;
float BAT_Voltage = 0;
float Resistance = 0;
float sample = 0;
bool calc = false, Done = false, Report_Info = true;

// Define global time variables
unsigned long previousMillis = 0;
const long interval = 50;  // Interval to update the battery icon
unsigned long startTime = 0;  // Store the start time for the entire process
unsigned long elapsedTime = 0;  // Total elapsed time

// Declare Hour, Minute, and Second globally
int Hour = 0;
int Minute = 0;
int Second = 0;

// Control pins
const byte PWM_Pin = D8;    // GPIO 8 on XIAO ESP32C3 (D8)
const byte Buzzer = D7;     // GPIO 7 on XIAO ESP32C3 (D7)
const int BAT_Pin = A0;     // GPIO 0 on XIAO ESP32C3 (A0)
const int Vref_Pin = A1;    // GPIO 1 on XIAO ESP32C3 (A1)
const byte Mosfet_Pin = D2; // GPIO 2 on XIAO ESP32C3 (D2)

// Battery level for icon
int batteryLevel = 0;

// Resistor values for the voltage divider
const float R1 = 200000.0;  // 200k ohms
const float R2 = 100000.0;  // 100k ohms

// ========================================= SETUP FUNCTION ========================================
void setup() {
    Serial.begin(115200);

    NimBLEDevice::init("TLMBeacon");
    NimBLEDevice::setPower(BEACON_POWER);

    // Get the device's address
    NimBLEAddress myAddress = NimBLEDevice::getAddress();
    Serial.printf("BLE MAC Address: %s\n", myAddress.toString().c_str());

    pAdvertising = NimBLEDevice::getAdvertising();

    // We'll rebuild the whole Service Data each iteration
    // because the MAC depends on the payload.
    pAdvertising->setConnectableMode(BLE_GAP_CONN_MODE_NON);
    uint16_t minInterval = ADV_INTERVAL_MS / 0.625; 
    uint16_t maxInterval = ADV_INTERVAL_MS / 0.625; // Set min and max to the same value for a fixed interval

    pAdvertising->setMinInterval(minInterval);
    pAdvertising->setMaxInterval(maxInterval);
    

    pinMode(PWM_Pin, OUTPUT);
    pinMode(Buzzer, OUTPUT);
    pinMode(Mosfet_Pin, OUTPUT);
    analogWrite(PWM_Pin, PWM_Value);
    UP_Button.begin();
    Down_Button.begin();
    Mode_Button.begin();

    // Initialize the OLED display with I2C address 0x3C
    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        for (;;); // Stop if OLED initialization fails
    }

    // Clear the buffer
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    // Display the Logo during startup 
    display.setTextSize(1);
    display.setCursor(25, 12);
    display.print("Lantau Hackers");
    display.setCursor(25, 40);
    display.print(myAddress.toString().c_str());
    display.display();
    delay(2000);

    // Start mode selection
    selectMode();

}



// ========================================= LOOP FUNCTION ========================================
void loop() {
    if (modeSelected) {
        if (selectedMode == 0) {
            chargeMode();
        } else if (selectedMode == 1) {
            dischargeMode();
        } else if (selectedMode == 2) {
            analyzeMode();
        } else if (selectedMode == 3) {
            internalResistanceMode();  // IR test mode added
        }
    }
}

// ========================================= MODE SELECTION ========================================
void selectMode() {
    modeSelected = false;
    selectedMode = 0;

    while (!modeSelected) {
        Mode_Button.read();
        UP_Button.read();
        Down_Button.read();

        // Handle UP button press (move up in the menu)
        if (UP_Button.isPressed() && UP_Button.lastChange() != upLastChange) {
            selectedMode = (selectedMode == 0) ? 3 : selectedMode - 1;  // If at the top, wrap around to the bottom
            beep(100);
            delay(100);  // Debounce delay to prevent multiple presses
        }

        // Handle DOWN button press (move down in the menu)
        if (Down_Button.isPressed() && Down_Button.lastChange() != downLastChange) {
            selectedMode = (selectedMode == 3) ? 0 : selectedMode + 1;  // If at the bottom, wrap around to the top
            beep(100);
            delay(100);  // Debounce delay to prevent multiple presses
        }

        // Confirm selection with MODE button press
        if (Mode_Button.isPressed() && Mode_Button.lastChange() != modeLastChange) {
            beep(300);
            modeSelected = true;
            delay(100);  // Debounce delay to prevent multiple presses
        }

        upLastChange = UP_Button.lastChange();
        downLastChange = Down_Button.lastChange();
        modeLastChange = Mode_Button.lastChange();

        // Display the menu options and highlight the selected one
        display.clearDisplay();
        display.setTextSize(1);
        display.setCursor(25, 0);
        display.print("Select Mode:");
        display.setCursor(25, 12);
        display.print((selectedMode == 0) ? "> Charge" : "  Charge");
        display.setCursor(25, 26);
        display.print((selectedMode == 1) ? "> Discharge" : "  Discharge");
        display.setCursor(25, 40);
        display.print((selectedMode == 2) ? "> Analyze" : "  Analyze");
        display.setCursor(25, 54);
        display.print((selectedMode == 3) ? "> IR Test" : "  IR Test");
        display.display();
    }

    // Show the selected mode after selection
    display.clearDisplay();
    display.setTextSize(2);
    display.setCursor(10, 20);
    if (selectedMode == 0) {
        display.print("Charge..");
    } else if (selectedMode == 1) {
        display.print("Dischrg..");
    } else if (selectedMode == 2) {
        display.print("Analyze..");
    } else if (selectedMode == 3) {
        display.print("IR Test..");
    }
    display.display();
    delay(500);
}

// ========================================= MEASURE BATTERY VOLTAGE ========================================
float measureVcc() {
    float vrefSum = 0;  // Sum of all the Vref readings
    for (int i = 0; i < 100; i++) {
        vrefSum += analogRead(Vref_Pin);  // Read raw analog value from Vref pin 100 times
        delay(2);  // Small delay between each reading for stability
    }
    float averageVrefReading = vrefSum / 100.0;  // Calculate the average Vref reading
    float vcc = (Vref_Voltage * 4096.0) / averageVrefReading;  // Calculate Vcc using average Vref and 12-bit ADC
    return vcc;
}

float measureBatteryVoltage() {
    Vcc = measureVcc();  // Measure the actual Vcc
    float batterySum = 0;  // Sum of all the battery readings
    for (int i = 0; i < 100; i++) {
        batterySum += analogRead(BAT_Pin);  // Read raw analog value from the battery pin 100 times
        delay(2);  // Small delay between each reading for stability
    }
    float averageBatteryReading = batterySum / 100.0;  // Calculate the average battery reading
    float voltageDividerRatio = (R1 + R2) / R2;
    float batteryVoltage = (averageBatteryReading * Vcc / 4096.0) * voltageDividerRatio;      // Convert ADC value to battery voltage
    return batteryVoltage;
}

// ========================================= UPDATE THE ELAPSED TIME =============================
void updateTiming() {
    unsigned long currentMillis = millis();
    elapsedTime = currentMillis - startTime;  // Calculate total elapsed time since the process started

    // Convert elapsed time to hours, minutes, and seconds
    Second = (elapsedTime / 1000) % 60;
    Minute = (elapsedTime / (1000 * 60)) % 60;
    Hour = (elapsedTime / (1000 * 60 * 60));
}

// ========================================= CHARGE MODE ========================================
void chargeMode() {
    calc = true;
    Done = false;
    Capacity = 0;  // Reset capacity for the test
    unsigned long lastUpdateTime = millis();  // Start timer for the charging process
    batteryLevel = 0;  // Start from 0%

    // Measure battery voltage before starting the charge
    BAT_Voltage = measureBatteryVoltage();

    // Check if the battery voltage is below the minimum threshold
    if (BAT_Voltage < NO_BAT_level) {
        // If battery voltage is below NO_BAT_level, display "No Battery"
        display.clearDisplay();
        display.setTextSize(1);
        display.setCursor(15, 25);
        display.print("EMPTY BAT SLOT");
        display.display();
        delay(3000);  // Wait for 3 seconds
        selectMode();  // Return to mode selection
        return;
    } else if (BAT_Voltage < DAMAGE_BAT_level) {
        // If battery voltage is below DAMAGE_BAT_level but above NO_BAT_level, consider the battery damaged
        display.clearDisplay();
        display.setTextSize(1);
        display.setCursor(25, 25);
        display.print("BAT DAMAGED");
        display.display();
        delay(3000);  // Wait for 3 seconds
        selectMode();  // Return to mode selection
        return;
    } 

    // If the battery voltage is between Min_BAT_level and FULL_BAT_level, proceed with charging
    digitalWrite(Mosfet_Pin, HIGH);  // Turn on MOSFET to start charging

    while (!Done) {
        updateTiming();
        BAT_Voltage = measureBatteryVoltage();  // Measure battery voltage    
        display.clearDisplay();
        // Simulate battery charging progression
        updateBatteryDisplay(true);  // True indicates charging
        display.setTextSize(1);
        display.setCursor(25, 5);
        display.print("Charging..");
        display.setCursor(40, 25);
        display.print(Hour);
        display.print(":");
        display.print(Minute);
        display.print(":");
        display.print(Second);       
        display.setTextSize(2);
        display.setCursor(15, 40);
        display.print("V:");
        display.print(BAT_Voltage,2);
        display.print("V");
        display.display();

        bool voltage_changed = (lastAdvertisedVoltage != BAT_Voltage);
        bool ten_sec_since_last_beacon = (elapsedTime - lastAdvertisedTimestamp) > 10000;
        if (voltage_changed && ten_sec_since_last_beacon) {
            lastAdvertisedVoltage = BAT_Voltage;
            lastAdvertisedTimestamp = elapsedTime;
            advertiseBeacon();
        }

        // Check if battery voltage has reached the full battery level
        if (BAT_Voltage >= FULL_BAT_level) {
            Done = true;
            digitalWrite(Mosfet_Pin, LOW);  // Turn off MOSFET to stop charging
            beep(300);  // Beep to indicate charging is complete
            displayFinalCapacity(Capacity_f, true);  // Pass true for charging complete            
        }  
        //  delay(100);      
    }
    selectMode();  // Return to mode selection after charging is complete
}

// ========================================= DISCHARGE MODE ========================================
void dischargeMode() {
    bool cutoffSelected = selectCutoffVoltage();
    bool currentSelected = selectDischargeCurrent();

    if (cutoffSelected && currentSelected) {
        calc = true;
        Done = false;
        Capacity = 0;  // Reset capacity for the test
        unsigned long lastUpdateTime = millis();  // Start timer for the discharging process

        digitalWrite(Mosfet_Pin, LOW);  // Ensure the charging MOSFET is off
        analogWrite(PWM_Pin, PWM_Value);  // Start discharging by applying PWM to the load

        while (!Done) {
            updateTiming();
            BAT_Voltage = measureBatteryVoltage();  // Measure the battery voltage

            // Calculate time elapsed since the last update
            unsigned long currentTime = millis();
            float elapsedTimeInHours = (currentTime - lastUpdateTime) / 3600000.0;  // Convert ms to hours

            // Update capacity using I * t (Current * elapsed time)
            if (calc) {
                Capacity_f += (Current[PWM_Index] + currentOffset) * elapsedTimeInHours;  // Capacity in mAh
                lastUpdateTime = currentTime;  // Update last update time
            }

            display.clearDisplay();
            updateBatteryDisplay(false);  // Update battery icon (false for discharging)
            display.setTextSize(1);
            display.setCursor(15, 5);
            display.print("Discharging..");
            display.setCursor(15, 20);
            display.print("Time: ");
            display.print(Hour);
            display.print(":");
            display.print(Minute);
            display.print(":");
            display.print(Second);
            display.setCursor(15, 35);
            display.print("Cap:");
            display.print(Capacity_f, 1);
            display.print("mAh");
            display.setCursor(15, 50);
            display.print("V: ");
            display.print(BAT_Voltage, 2);
            display.print("V");
            display.display();

            bool voltage_changed = (lastAdvertisedVoltage != BAT_Voltage);
            bool ten_sec_since_last_beacon = (elapsedTime - lastAdvertisedTimestamp) > 10000;
            if (voltage_changed && ten_sec_since_last_beacon) {
                lastAdvertisedVoltage = BAT_Voltage;
                lastAdvertisedTimestamp = elapsedTime;
                advertiseBeacon();
            }

            if (BAT_Voltage <= cutoffVoltage) {
                Done = true;
                analogWrite(PWM_Pin, 0);  // Stop discharging by turning off the load (PWM)
                beep(300);  // Long beep to indicate discharging is complete
                displayFinalCapacity(Capacity_f, false);  // Pass false for discharging complete
            }
          //  delay(100);
        }
    }
    selectMode();  // Return to mode selection after discharging is complete
}

// ========================================= ANALYZE MODE ========================================
void analyzeMode() {
    inAnalyzeMode = true;  // Set analyze mode flag to true
    calc = true;
    Done = false;
    Capacity = 0;  // Reset capacity for this test
    unsigned long lastUpdateTime = millis();  // Start the timer for the entire analyze process

    // Step 1: Check if the battery is damaged, missing, or already full
    BAT_Voltage = measureBatteryVoltage();

    // Check if the battery voltage is below the minimum threshold
    if (BAT_Voltage < NO_BAT_level) {
        // If battery voltage is below NO_BAT_level, display "No Battery"
        display.clearDisplay();
        display.setTextSize(1);
        display.setCursor(15, 25);
        display.print("EMPTY BAT SLOT");
        display.display();
        delay(3000);  // Wait for 3 seconds
        selectMode();  // Return to mode selection
        return;
    } else if (BAT_Voltage < DAMAGE_BAT_level) {
        // If battery voltage is below DAMAGE_BAT_level but above NO_BAT_level, consider the battery damaged
        display.clearDisplay();
        display.setTextSize(1);
        display.setCursor(25, 25);
        display.print("BAT DAMAGED");
        display.display();
        delay(3000);  // Wait for 3 seconds
        selectMode();  // Return to mode selection
        return;
    }

    // Step 2: Charge the battery until full
    digitalWrite(Mosfet_Pin, HIGH);  // Turn on MOSFET to start charging

    while (!Done) {
        updateTiming();
        BAT_Voltage = measureBatteryVoltage();  // Measure battery voltage    
        display.clearDisplay();
        // Simulate battery charging progression
        updateBatteryDisplay(true);  // True indicates charging
        display.setTextSize(1);
        display.setCursor(10, 5);
        display.print("Analyzing - C");
        display.setCursor(40, 25);
        display.print(Hour);
        display.print(":");
        display.print(Minute);
        display.print(":");
        display.print(Second);       
        display.setTextSize(2);
        display.setCursor(15, 40);
        display.print("V:");
        display.print(BAT_Voltage,2);
        display.print("V");
        display.display();

        bool voltage_changed = (lastAdvertisedVoltage != BAT_Voltage);
        bool ten_sec_since_last_beacon = (elapsedTime - lastAdvertisedTimestamp) > 10000;
        if (voltage_changed && ten_sec_since_last_beacon) {
            lastAdvertisedVoltage = BAT_Voltage;
            lastAdvertisedTimestamp = elapsedTime;
            advertiseBeacon();
        }

        // Check if battery voltage has reached the full battery level
        if (BAT_Voltage >= FULL_BAT_level) {
            Done = true;
            digitalWrite(Mosfet_Pin, LOW);  // Turn off MOSFET to stop charging
        }
        //delay(100);
    }

    // Step 3: Rest for 5 minutes to allow the battery to stabilize
    display.clearDisplay();
    display.setTextSize(2);
    display.setCursor(5, 25);
    display.print("Resting..");
    display.display();
    delay(180000);  // Wait for 3 minutes (180000 ms)

    // Step 4: Discharge the battery at 500mA to calculate real capacity
    cutoffVoltage = 3.0;  // Set cutoff voltage for discharge
    PWM_Index = 6;  // Index for 500mA discharge current in the Current array
    PWM_Value = PWM[PWM_Index];  // Set PWM value for 500mA discharge

    Done = false;
    Capacity = 0;  // Reset capacity for this test
    lastUpdateTime = millis();  // Reset the start time for discharge process
    digitalWrite(Mosfet_Pin, LOW);  // Ensure the charging MOSFET is off
    analogWrite(PWM_Pin, PWM_Value);  // Start discharging   

    while (!Done) {
        updateTiming();
        BAT_Voltage = measureBatteryVoltage();  // Measure the battery voltage

        // Calculate time elapsed since the last update
        unsigned long currentTime = millis();
        float elapsedTimeInHours = (currentTime - lastUpdateTime) / 3600000.0;  // Convert ms to hours

        // Update capacity using I * t (Current * elapsed time)
        if (calc) {
            Capacity_f += (Current[PWM_Index] + currentOffset) * elapsedTimeInHours;  // Capacity in mAh
            lastUpdateTime = currentTime;  // Update last update time
        }

        display.clearDisplay();
        updateBatteryDisplay(false);  // Update battery icon (false for discharging)
        display.setTextSize(1);
        display.setCursor(10, 5);
        display.print("Analyzing - D");
        display.setCursor(15, 20);
        display.print("Time: ");
        display.print(Hour);
        display.print(":");
        display.print(Minute);
        display.print(":");
        display.print(Second);
        display.setCursor(15, 35);
        display.print("Cap:");
        display.print(Capacity_f, 1);
        display.print("mAh");
        display.setCursor(15, 50);
        display.print("V: ");
        display.print(BAT_Voltage, 2);
        display.print("V");
        display.display();

        bool voltage_changed = (lastAdvertisedVoltage != BAT_Voltage);
        bool ten_sec_since_last_beacon = (elapsedTime - lastAdvertisedTimestamp) > 10000;
        if (voltage_changed && ten_sec_since_last_beacon) {
            lastAdvertisedVoltage = BAT_Voltage;
            lastAdvertisedTimestamp = elapsedTime;
            advertiseBeacon();
        }

        if (BAT_Voltage <= cutoffVoltage) {
            Done = true;
            analogWrite(PWM_Pin, 0);  // Stop discharging by turning off the load (PWM)
            beep(300);  // Long beep to indicate discharging is complete
            displayFinalCapacity(Capacity_f, false);  // Pass false for discharging complete
        }
        //  delay(100);
    }       

    inAnalyzeMode = false;  // Reset analyze mode flag
    selectMode();  // Return to mode selection after analyzing
}

// ========================================= INTERNAL RESISTANCE MODE ========================================
void internalResistanceMode() {
    float voltageNoLoad = 0;
    float voltageLoad = 0;
    float internalResistance = 0;
    bool resistanceMeasured = false;

    digitalWrite(Mosfet_Pin, LOW);  // Ensure the charging MOSFET is off

    // Step 1: Measure voltage without load (open circuit)
    analogWrite(PWM_Pin, 0);  // Ensure no current flows through the load
    delay(500);  // Let the voltage stabilize
    voltageNoLoad = measureBatteryVoltage();  // Measure voltage with no load

    // Step 2: Apply load using PWM
    PWM_Index = 6;  // Index corresponding to 1A current in the Current array
    PWM_Value = PWM[PWM_Index];  // Set PWM value corresponding to 1A current
    analogWrite(PWM_Pin, PWM_Value);  // Apply PWM to control load

    delay(500);  // Let the voltage stabilize under load
    voltageLoad = measureBatteryVoltage();  // Measure the loaded voltage

    // Calculate the load current and internal resistance using Ohm's Law
    float currentDrawn = Current[PWM_Index] / 1000.0;     // Convert current in mA to Amps  

    // Step 4: Calculate internal resistance using Ohm's Law
    if (currentDrawn > 0) {
        internalResistance = (voltageNoLoad - voltageLoad) / currentDrawn;  // R = (V_no_load - V_load) / I
    } else {
        internalResistance = 0;  // Avoid division by zero
    }

    // Display the IR test results
    displayIRTestIcon(voltageNoLoad, voltageLoad, internalResistance);

    // Beep to indicate completion of the IR measurement
    beep(300);

    // Step 5: Turn off the load after measurement
    analogWrite(PWM_Pin, 0);  // Stop the current flow
    delay(5000);  // Wait for the user to read the display

    resistanceMeasured = true;

    // Return to the mode selection if measurement is complete
    if (resistanceMeasured) {
        selectMode();
    }
}

// ========================================= FINAL CAPACITY DISPLAY ON OLED ========================================
void displayFinalCapacity(float capacity, bool chargingComplete) {
    display.clearDisplay();

    // Display "Complete" message and final capacity
    display.setTextSize(1);
    display.setCursor(15, 5);
    display.print("Complete");
    display.setCursor(15, 20);
    display.print("Time: ");
    display.print(Hour);
    display.print(":");
    display.print(Minute);
    display.print(":");
    display.print(Second);
    display.setCursor(15, 35);
    display.print("Cap:");
    display.print(Capacity_f, 1);
    display.print("mAh");
    display.setCursor(15, 50);
    display.print("V: ");
    display.print(BAT_Voltage,2);
    display.print("V");

    // Display battery icon full (charging complete) or empty (discharging complete)
    if (chargingComplete) {
        drawBatteryOutline();  // Draw the battery outline
        drawBatteryFill(100);  // Battery full when charge is complete
    } else {
        drawBatteryOutline();  // Draw the battery outline
        drawBatteryFill(0);    // Battery empty when discharge is complete
    }

    display.display();  // Update the OLED display

    // Keep the screen on until a button is pressed
    bool buttonPressed = false;
    while (!buttonPressed) {
        Mode_Button.read();
        UP_Button.read();
        Down_Button.read();

        if (Mode_Button.wasPressed() || UP_Button.wasPressed() || Down_Button.wasPressed()) {
            buttonPressed = true;
        }

        delay(100);  // Polling delay to reduce the button read frequency
    }

    // Once a button is pressed, return to mode selection
    selectMode();
}

// ========================================= SELECT CUTOFF VOLTAGE ========================================
bool selectCutoffVoltage() {
    bool cutoffSelected = false;
    while (!cutoffSelected) {
        UP_Button.read();
        Down_Button.read();
        Mode_Button.read();

        // Increase cutoff voltage with UP button
        if (UP_Button.isPressed() && cutoffVoltage < Max_BAT_level && UP_Button.lastChange() != upLastChange) {
            cutoffVoltage += 0.1;
            beep(100);
            delay(300);
        }

        // Decrease cutoff voltage with DOWN button
        if (Down_Button.isPressed() && cutoffVoltage > Min_BAT_level && Down_Button.lastChange() != downLastChange) {
            cutoffVoltage -= 0.1;
            beep(100);
            delay(300);
        }

        // Confirm cutoff voltage with MODE button
        if (Mode_Button.isPressed() && Mode_Button.lastChange() != modeLastChange) {
            cutoffSelected = true;
            beep(300);
        }

        // Update OLED with selected cutoff voltage
        display.clearDisplay();
        display.setTextSize(1);
        display.setCursor(2, 10);
        display.print("Select Cutoff Volt:");
        display.setTextSize(2);
        display.setCursor(20, 30);
        display.print("V:");
        display.print(cutoffVoltage, 1);
        display.print("V");
        display.display();
    }
    return cutoffSelected;
}

// ========================================= SELECT DISCHARGE CURRENT ========================================
bool selectDischargeCurrent() {
    bool currentSelected = false;
    PWM_Index = 0;
    PWM_Value = PWM[PWM_Index];

    while (!currentSelected) {
        UP_Button.read();
        Down_Button.read();
        Mode_Button.read();

        // Increase discharge current with UP button
        if (UP_Button.isPressed() && PWM_Index < (Array_Size - 1) && UP_Button.lastChange() != upLastChange) {
            PWM_Value = PWM[++PWM_Index];
            beep(100);
            delay(300);
        }

        // Decrease discharge current with DOWN button
        if (Down_Button.isPressed() && PWM_Index > 0 && Down_Button.lastChange() != downLastChange) {
            PWM_Value = PWM[--PWM_Index];
            beep(100);
            delay(300);
        }

        // Confirm current selection with MODE button
        if (Mode_Button.isPressed() && Mode_Button.lastChange() != modeLastChange) {
            currentSelected = true;
            beep(300);
        }

        // Update the OLED display with the selected current
        display.clearDisplay();
        display.setTextSize(1);
        display.setCursor(2, 10);
        display.print("Select Dischrg Curr:");
        display.setTextSize(2);
        display.setCursor(15, 30);
        display.print("I:");
        display.print(Current[PWM_Index]);
        display.print("mA");
        display.display();
    }
    return currentSelected;
}

// ========================================= DRAW BATTERY ICON AND ANIMATE ========================================
void drawBatteryOutline() {
    display.drawRect(100, 15, 12, 20, SSD1306_WHITE);  // Adjusted Y-axis for the Battery box (12x20 size)
    display.drawRect(102, 12, 8, 3, SSD1306_WHITE);    // Adjusted Y-axis for the Battery head (8x3 size)
}

// Fill the battery based on the level (for both charging and discharging)
void drawBatteryFill(int level) {
    int fillHeight = map(level, 0, 100, 0, 18);  // Map level to height (0-18 pixels)
    display.fillRect(102, 33 - fillHeight, 8, fillHeight, SSD1306_WHITE);  // Adjusted Y-axis for bottom fill
}

// Update the battery display during charge/discharge
void updateBatteryDisplay(bool charging) {
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis >= interval) {
        previousMillis = currentMillis;

        // Modify the battery level behavior based on charging or discharging
        if (charging) {
            batteryLevel += 4;  // Faster fill for charge mode
            if (batteryLevel > 100) batteryLevel = 0;  // Reset to 0% when reaching 100%
        } else {
            batteryLevel -= 4;  // Faster depletion for discharge mode
            if (batteryLevel < 0) batteryLevel = 100;  // Reset to 100% when reaching 0%
        }

        // Clear and draw the updated battery icon
        drawBatteryOutline();
        drawBatteryFill(batteryLevel);
    }
}

// ========================================= DRAW ICON FOR IR TEST ========================================
void displayIRTestIcon(float voltageNoLoad, float voltageLoad, float internalResistance) {
    display.clearDisplay();

    // Drawing a resistor-like icon (simple lines and zig-zag), centered horizontally and shifted 5 pixels up
    display.drawLine(34, 15, 54, 15, SSD1306_WHITE);  // Straight line
    display.drawLine(54, 15, 59, 20, SSD1306_WHITE);  // Zigzag start
    display.drawLine(59, 20, 64, 10, SSD1306_WHITE);  // Zigzag mid
    display.drawLine(64, 10, 69, 20, SSD1306_WHITE);  // Zigzag mid
    display.drawLine(69, 20, 74, 15, SSD1306_WHITE);  // Zigzag end
    display.drawLine(74, 15, 94, 15, SSD1306_WHITE);  // Straight line

    display.setTextSize(2);
    display.setCursor(2, 35);
    display.print("IR:");
    display.print(internalResistance * 1000, 0);  // Display internal resistance in milliohms
    display.print("mOhm");
    display.display();  // Update the OLED display
}

// ========================================= BUZZER BEEP ========================================
void beep(int duration) {
    digitalWrite(Buzzer, HIGH);
    delay(duration);
    digitalWrite(Buzzer, LOW);
}

// ========================================= HMAC SUPPORT ========================================

// ------------------------------------------------------------------
// 2️⃣ Helper: compute truncated HMAC‑SHA256 -----------------------
void compute_hmac(char *key, char *payload, size_t payloadLength, uint8_t *out, size_t out_len)
{
  byte hmacResult[32];

  mbedtls_md_context_t ctx;
  mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;
 
  //const size_t payloadLength = strlen(payload);
  const size_t keyLength = strlen(key);               
 
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char *) key, keyLength);
  mbedtls_md_hmac_update(&ctx, (const unsigned char *) payload, payloadLength);
  mbedtls_md_hmac_finish(&ctx, hmacResult);
  mbedtls_md_free(&ctx);
 
  Serial.print("\nHash: ");
  printHex(hmacResult, sizeof(hmacResult));

  // Copy only the first `out_len` bytes (truncated MAC)
  memcpy(out, hmacResult, out_len);

  Serial.print("\nOut: ");
  printHex(out, out_len);
}

void printHex(byte * byteArray, size_t byteArraySize) {
  for(int i= 0; i< byteArraySize; i++){
      char str[3];
 
      sprintf(str, "%02x", (int)byteArray[i]);
      Serial.print(str);
  }
}

// ========================================= BLUETOOTH SUPPORT ========================================

// Check
// https://github.com/google/eddystone/blob/master/eddystone-tlm/tlm-plain.md
// and http://www.hugi.scene.org/online/coding/hugi%2015%20-%20cmtadfix.htm
// for the temperature value. It is a 8.8 fixed-point notation
void setBeacon() {
    NimBLEEddystoneTLM eddystoneTLM;
    eddystoneTLM.setVolt(ENDIAN_CHANGE_U16((uint16_t)(BAT_Voltage*1000))); // 3300mV = 3.3V
    eddystoneTLM.setTemp(ENDIAN_CHANGE_U16((uint16_t)(Resistance*1000)));  // 3000 = 30.00 ˚C
    eddystoneTLM.setTime(ENDIAN_CHANGE_U32((uint32_t)elapsedTime));
    eddystoneTLM.setCount(ENDIAN_CHANGE_U32((uint32_t)count++));
    //eddystoneTLM.setVolt(ENDIAN_CHANGE_U16((uint16_t)3765)); // 3300mV = 3.3V
    //eddystoneTLM.setTemp(ENDIAN_CHANGE_U16((uint16_t)1234));  // 3000 = 30.00 ˚C
    //eddystoneTLM.setTime(ENDIAN_CHANGE_U32((uint32_t)millis()));
    //eddystoneTLM.setCount(ENDIAN_CHANGE_U32((uint32_t)count++));

    //eddystoneTLM.setVolt(eddystoneTLM.getVolt()); /// Needed to fix inversion of endianness BUG
    //eddystoneTLM.setTemp(eddystoneTLM.getTemp());  // Needed to fix inversion of endianness BUG
    //eddystoneTLM.setTime(eddystoneTLM.getTime());
    //eddystoneTLM.setCount(eddystoneTLM.getCount());

    Serial.println();
    Serial.printf("Battery voltage is %d mV = 0x%04X\n", eddystoneTLM.getVolt() , eddystoneTLM.getVolt());
    Serial.printf("Resistance is: %d.%d 0x%04X\n", eddystoneTLM.getTemp(), eddystoneTLM.getTemp());
    Serial.printf("Count is: %d = 0x%04X\n", eddystoneTLM.getCount(), eddystoneTLM.getCount());
    Serial.printf("Time is: %d = 0x%04X\n", eddystoneTLM.getTime(), eddystoneTLM.getTime());


    pAdvertising->clearData();   // remove previous Service Data

    NimBLEAdvertisementData        oAdvertisementData = BLEAdvertisementData();
    NimBLEAdvertisementData        oScanResponseData  = BLEAdvertisementData();
    oAdvertisementData.setName("ESP32 TLM Beacon");
    pAdvertising->setAdvertisementData(oAdvertisementData);

    NimBLEEddystoneTLM::BeaconData beaconData         = eddystoneTLM.getData();
    int beaconDataSize = sizeof(beaconData);

    // ---- 3. Compute truncated HMAC over the 14‑byte payload ---------------
    uint8_t* tlm;
    tlm = reinterpret_cast<uint8_t*>(&beaconData); // 14 bytes payload


    // ---- 4. Assemble Service Data: UUID + TLM + MAC ----------------------
    const size_t SERVICE_DATA_LEN = beaconDataSize + MAC_TRUNC_LEN;
    uint8_t serviceData[SERVICE_DATA_LEN];
    memcpy(serviceData, tlm, beaconDataSize);

    uint8_t mac[MAC_TRUNC_LEN];
    //compute_hmac(tlm, beaconDataSize, mac, MAC_TRUNC_LEN);
    compute_hmac(HMAC_KEY, (char*)tlm, beaconDataSize, mac, MAC_TRUNC_LEN);
    Serial.print("\ntruncated mac ");
    printHex(mac, MAC_TRUNC_LEN);
    Serial.println();

    memcpy(serviceData + beaconDataSize, mac, MAC_TRUNC_LEN);
    Serial.print("payload = ");
    printHex(serviceData, beaconDataSize+MAC_TRUNC_LEN);
    Serial.println();

    oScanResponseData.setServiceData(NimBLEUUID("FEAA"),
                                     serviceData,
                                     beaconDataSize+MAC_TRUNC_LEN);
    pAdvertising->setScanResponseData(oScanResponseData);
}

void advertiseBeacon() {
    //gettimeofday(&nowTimeStruct, NULL);

    Serial.printf("Starting ESP32. Bootcount = %lu\n", bootcount++);
    //Serial.printf("Deep sleep (%llds since last reset, %llds since last boot)\n",
    //              nowTimeStruct.tv_sec,
    //              nowTimeStruct.tv_sec - last);
    //last = nowTimeStruct.tv_sec;
    
    setBeacon();
    if(true || BAT_Voltage > 0) {
        pAdvertising->start();
        Serial.println("Advertising ...");
        //delay(10000);
        //pAdvertising->stop();
    }

    //Serial.printf("Enter deep sleep for 10s\n");
    //esp_deep_sleep(1000000LL * GPIO_DEEP_SLEEP_DURATION);
} 
