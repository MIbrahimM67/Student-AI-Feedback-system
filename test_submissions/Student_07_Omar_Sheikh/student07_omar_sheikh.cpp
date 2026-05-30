// Student: Omar Sheikh | Level: EXCELLENT+ (10/10)
// Goes above and beyond: validates input, uses a function, handles float,
// loops to allow multiple attempts — demonstrates mastery

#include <iostream>
#include <limits>
using namespace std;

double sumTwoNumbers(double a, double b) {
    return a + b;
}

int main() {
    double num1, num2;
    
    cout << "=== Sum Calculator ===" << endl;
    
    // Input validation for num1
    while (true) {
        cout << "Enter first number: ";
        if (cin >> num1) break;
        cout << "Invalid input. Please enter a numeric value." << endl;
        cin.clear();
        cin.ignore(numeric_limits<streamsize>::max(), '\n');
    }
    
    // Input validation for num2
    while (true) {
        cout << "Enter second number: ";
        if (cin >> num2) break;
        cout << "Invalid input. Please enter a numeric value." << endl;
        cin.clear();
        cin.ignore(numeric_limits<streamsize>::max(), '\n');
    }
    
    double result = sumTwoNumbers(num1, num2);
    cout << "\nResult: " << num1 << " + " << num2 << " = " << result << endl;
    
    return 0;
}
