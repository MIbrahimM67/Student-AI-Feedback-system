// Student: Amna Rizvi | Level: GOOD (7/10)
// Correct program but the output message is confusing/misleading
// Also uses 'auto' keyword unnecessarily which is uncommon for intro courses
// Shows confidence but some conceptual gaps in communication

#include <iostream>
using namespace std;

int main() {
    auto first = 0;
    auto second = 0;
    
    cout << "Give me number 1: ";
    cin >> first;
    cout << "Give me number 2: ";
    cin >> second;
    
    auto answer = first + second;
    
    // Confusing output message
    cout << "The total multiplication of your two values gives: " << answer << endl;
    
    return 0;
}
